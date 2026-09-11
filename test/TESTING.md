# Plan testów wydajnościowych

Cztery mikrobenchmarki operacji z notebooka, uporządkowane od najprostszej do najbardziej
złożonej. Każdy porównuje skompilowaną ścieżkę RDataFrame z implementacjami pythonowymi.

Stała konfiguracja: **rp_id = 22** (pot typu box, ramię 45, 3 regiony).

| test | operacja | dlaczego w tej kolejności |
|---|---|---|
| TEST 1 | jeden filtr | najprostsza operacja, jedna gałąź, punkt odniesienia |
| TEST 2 | łańcuch filtrów | kompozycja predykatów, wiele gałęzi, eager vs lazy |
| TEST 3 | dopisanie efficiency | dodanie nowych danych do rekordów, obliczenia per track |
| TEST 4 | selekcja rozrzucona vs ciągła | czy filtrowanie kiedykolwiek zmniejsza I/O |

---

## Dwie decyzje metodologiczne, od których zależy reszta

### 1. Cztery fazy pomiaru, nie dwie

Każdy bieg raportuje `wall_setup`, `wall_warmup`, `wall_jit` i `wall_loop`. Tylko ostatnia
skaluje się z liczbą zdarzeń.

Podział nie jest kosmetyczny. W wersji dwufazowej `rdf-report` minus `rdf-lazy` wynosiło
+1.073, +1.089, +1.085, +1.088 i +1.088 s dla długości łańcucha 1–5 — stała niezależna
zarówno od liczby zdarzeń, jak i od odczytanych bajtów, przypisywana pętli zdarzeń. Po
rozdzieleniu faz ten koszt pojawia się w `wall_jit` (0.343 s lokalnie), a pętle obu
implementacji wychodzą równe (0.299 s vs 0.280 s). To **inny wniosek o `Report()`** niż ten,
który poprzednie liczby wspierały: `Report()` nie kosztuje pętli zdarzeń, kosztuje budowy grafu.

`rdf-eager` jest jedynym wyjątkiem i celowo nie ma fazy `jit`: deklaruje kolejny filtr dopiero
po odczytaniu poprzedniej liczności, więc budowa grafu jest u niego nierozdzielna od pętli.
Tak właśnie działa `rdata_analysis()`, więc to zachowanie badane, nie artefakt.

### 2. `python` to ścieżka materializacji PyROOT, a nie „implementacja NumPy"

`AsNumpy()` na gałęzi jagged zwraca tablicę NumPy **obiektów RVec** — po jednym na zdarzenie.
Żadna operacja na tym nie uniknie pętli po zdarzeniach w Pythonie, i pomiary to mówią:

- tryb „wektorowy" nie jest szybszy od naiwnego (4.20 s vs 2.86 s w TEŚCIE 1),
- łańcuch w TEŚCIE 2 kosztuje 1.61 s przy długości 1, gdzie jedyna kolumna jest płaskim
  intem, i 25.6 s przy długości 2, gdzie pojawia się pierwsza gałąź jagged.

Dlatego doszła implementacja **`uproot`** (uproot + awkward): prawdziwa reprezentacja kolumnowa
— płaski bufor wartości plus offsety — z operacjami w kodzie skompilowanym. Bez niej
porównanie idzie ze słomianym przeciwnikiem, a wniosek „RDataFrame jest o rzędy wielkości
szybszy od NumPy" jest częściowo artefaktem sposobu wczytywania danych. Zmierzone na
`examples/test.root`, łańcuch 5 filtrów:

| implementacja | pętla |
|---|---|
| `rdf-lazy` | 0.12 s |
| `uproot` | 0.21 s |
| `python` (AsNumpy) | 8.66 s |

Czyli realna przewaga RDataFrame nad porządnym kodem kolumnowym w Pythonie to **~1.7×**, a nie
~70×. Obie liczby są prawdziwe — mierzą różne rzeczy, i praca powinna podawać tę pierwszą jako
porównanie implementacji, a tę drugą jako koszt PyROOT-owego `AsNumpy`.

---

## TEST 1 — pojedynczy filtr (`decRPId == 22`)

Selekcja zdarzeń zawierających przynajmniej jeden track w danym pocie.

| impl | co robi |
|---|---|
| `rdf` | `df.Filter("Any(PPSLocalTrack_decRPId == 22)")` + `Count()` |
| `rdf --filter-style callable` | to samo, ale ciało predykatu w funkcji zadeklarowanej raz; clingowi zostaje jednolinijkowe wywołanie |
| `python --mode vector` | `AsNumpy`, spłaszczenie jagged, maska `flat == 22` |
| `python --mode loop` | `sum(1 for a in arrays if 22 in a)` |
| `uproot` | `ak.any(decRPId == 22, axis=1)` na tablicy awkward |

- **Wynik kontrolny**: liczba zdarzeń przechodzących filtr (59 946).
- **Czego dowodzi**: RDF czyta jedną gałąź strumieniowo i nie materializuje nic;
  `python` musi wciągnąć całą kolumnę jagged do RAM zanim cokolwiek policzy. `uproot`
  materializuje też, ale jako płaskie bufory — to rozdziela „materializacja jest droga" od
  „obiekty per zdarzenie z PyROOT są drogie".

`--filter-style` odpowiada na osobne pytanie: ile ze stałego kosztu to kompilacja samego ciała
predykatu, a ile własna księgowość RDataFrame. To realna mitygacja, nie sztuczna — dokładnie to
zrobiłby użytkownik po zauważeniu, że setup dominuje krótki bieg.

---

## TEST 2 — łańcuch filtrów: eager vs lazy + selektywność kolumnowa

Łańcuch z notebooka, rozszerzony do pięciu kroków. `--chain-len 1..5` steruje, ile z nich
zostanie nałożonych — kumulatywnie, w tej kolejności:

| krok | filtr | gałąź | zdarzeń po filtrze |
|---|---|---|---|
| 1 | `nPPSLocalTrack > 0` | `nPPSLocalTrack` | 311 565 |
| 2 | `filter_double_arm_events` | + `PPSLocalTrack_decRPId` | 276 737 |
| 3 | `filter_detector_type("diamond")` | + `PPSLocalTrack_rpType` | 75 275 |
| 4 | `filter_detector_specific_events(22)` | — (reużywa `decRPId`) | 59 946 |
| 5 | `filter_xi_ranged_events(0.05, 0.1)` | + `Proton_singleRP_xi` | 54 156 |

(z 346 825 zdarzeń w `examples/test.root`)

Krok 4 jest w łańcuchu celowo: jako jedyny **nie** dodaje nowej gałęzi. Dzięki temu widać,
że odczyt rośnie z liczbą *kolumn*, a nie z liczby *filtrów*.

**Punkty pomiarowe:**

| impl | co robi | co mierzy |
|---|---|---|
| `rdf-lazy` | cały łańcuch `Filter`, jedno `Count()` na końcu | 1 pętla zdarzeń |
| `rdf-eager` | `Count()` na starcie i po każdym filtrze — dokładnie to, co robi `rdata_analysis` | `chain_len + 1` pętli |
| `rdf-report` | łańcuch + `Report()` na końcu | liczności wszystkich filtrów w jednej pętli |
| `python` | `AsNumpy` potrzebnych kolumn, potem maski sekwencyjnie | koszt materializacji PyROOT |
| `uproot` | te same maski na tablicach awkward | koszt kodu kolumnowego w Pythonie |

Wszystkie dają identyczne liczności pośrednie (sprawdza `validate.py`). Różni je liczba
przebiegów i odczyt:

| chain-len | `rdf-lazy` | `rdf-report` | `rdf-eager` | `python` |
|---|---|---|---|---|
| 1 | 0.21 MB / 1 pętla | 0.21 MB / 1 | 0.21 MB / 2 | 0.21 MB / 1 |
| 2 | 0.99 / 1 | 0.99 / 1 | 1.20 / 3 | 0.99 / 1 |
| 3 | 1.47 / 1 | 1.47 / 1 | 2.66 / 4 | 1.47 / 1 |
| 4 | 1.47 / 1 | 1.47 / 1 | 4.13 / 5 | 1.47 / 1 |
| 5 | 5.40 / 1 | 5.40 / 1 | **9.53 / 6** | 5.40 / 1 |

- **Czego dowodzi**:
  1. `rdf-eager` vs `rdf-lazy` — koszt wypisywania statystyk po każdym kroku: 6 przebiegów
     zamiast jednego i **1.8× więcej odczytanych bajtów**. Nadmiarowy odczyt ma konkretną
     przyczynę: przy deklarowaniu gałęzi po jednej na przebieg `TTreeCache` nigdy nie poznaje
     ich wszystkich naraz.
  2. `rdf-report` daje te same statystyki w jednej pętli i przy tym samym odczycie co wersja
     leniwa — gotowa rekomendacja zmiany w `rdata_analysis`. Po rozdzieleniu faz widać, że
     jego narzut (~0.34 s) to jednorazowa budowa grafu, nie koszt na zdarzenie: **przy
     dłuższym biegu jest bezpłatny**.
  3. **Selektywność kolumnowa**: pełny łańcuch odczytuje 5.4 MB z pliku 240 MB o 1984
     gałęziach — 2.2% pliku. Ważniejsza jest jednak druga miara, `read_amplification`:
     5.40 MB / 5.20 MB skompresowanego rozmiaru nazwanych gałęzi = **1.04**. RDataFrame czyta
     to, o co poproszono, i praktycznie nic więcej.
  4. Pamięć Pythona rośnie z liczbą materializowanych kolumn, RDF nie.

> **Zmierzone, wbrew pierwotnej hipotezie:** `rdf-lazy` odczytuje *tyle samo* bajtów co ścieżka
> pythonowa na każdej długości łańcucha. Zakładałam, że późniejsze gałęzie będą czytane tylko
> dla zdarzeń, które dotarły do danego węzła, więc odczyt będzie rósł subliniowo. Tak nie jest:
> ROOT czyta całe **koszyki**, a przefiltrowane zdarzenia są rozrzucone po wszystkich koszykach
> danej gałęzi, więc każdy i tak trzeba zdekompresować. Krótkie spięcie predykatów oszczędza
> CPU, nie I/O.
>
> To jednak **hipoteza o tym, gdzie leżą ocalałe zdarzenia**, a nie stwierdzenie o filtrowaniu
> jako takim — i jest sprawdzalna. Robi to TEST 4; do czasu jego rozstrzygnięcia zdanie powyżej
> trzeba czytać jako wyjaśnienie kandydackie.

`--chain-order selective-first` stawia na początku krok, który cięcie robi najmocniej
(`diamond`: 276 737 → 75 275), żeby trzy pozostałe predykaty działały na ćwiartce zdarzeń.
RDataFrame nigdy nie przestawia predykatów sam, więc kolejność jest decyzją użytkownika i
kosztuje. Predykaty są koniunkcją, więc każda kolejność daje tę samą liczność końcową — i to
właśnie pozwala czytać ten eksperyment jako czystą różnicę kosztu, a nie jako dwa różne
zapytania. `validate.py` to sprawdza.

---

## TEST 3 — dołożenie efficiency do każdego rekordu

Dla każdego tracka: przypisanie regionu diamentu i odczyt efficiency. Wejście: DataFrame
przefiltrowany po `decRPId == 22`. Filtr i budowa JSON-a należą do setupu — koszt filtra jest
już zmierzony w TEŚCIE 1.

| impl | co robi | co mierzy |
|---|---|---|
| `correctionlib` | pętla po trackach, `corr.evaluate(region_idx)` per track przez Python API | realny koszt ewaluacji correctionlib |
| `jit` | `corr.evaluate` 3× przy setupie → LUT jako `constexpr std::array` w kernelu C++, jeden `Define` | zysk z kompilacji |
| `python` | bez correctionlib i bez JSON, geometria i wartości zakodowane wprost | rozwiązanie „ręczne" |
| `uproot` | ta sama geometria i ten sam LUT na tablicach awkward | to samo poza ROOT-em |

Jeden tryb geometrii: **`rotated`**. Wariant `bbox` (osiowe zakresy x/y) odrzucony — geometria
pota faktycznie jest obrócona, więc wersja bez rotacji nie jest alternatywą, tylko błędnym
obliczeniem.

- **Wyniki kontrolne**: suma efficiency po wszystkich trackach, liczba tracków z eff > 0.
  Wszystkie cztery implementacje dają `eff_sum = 62512.3106` i `eff_hits = 64862`; ścieżka
  `jit` różni się na dziesiątej cyfrze znaczącej, co jest kolejnością sumowania `float`,
  a nie inną odpowiedzią.

> **Czego ten test nie pokazuje.** Naturalne odczytanie tabeli powyżej — że `correctionlib`
> jest droga i dlatego warto ją zastąpić — nie ma poparcia w liczbach. Zmierzone:
> `correctionlib` 2.64 s vs ręczna geometria 2.55 s, czyli +3.5%, w granicach szumu między
> biegami. Oba warianty dzielą to samo `AsNumpy` i to ono dominuje: `uproot` z tym samym LUT
> i tą samą geometrią robi to w 0.49 s, a `jit` w 0.37 s. **Koszt leży w materializacji
> kolumn przez PyROOT, nie w correctionlib** — i tak trzeba go opisać, bo inaczej praca
> rekomenduje optymalizację rzeczy, która nie jest wąskim gardłem.

---

## TEST 4 — czy selekcja wierszy kiedykolwiek zmniejsza I/O

Dwa zapytania zachowują porównywalny odsetek zdarzeń i kończą tą samą redukcją po tej samej
gałęzi (`Proton_singleRP_xi`). Różnią się tylko tym, czy ocalałe zdarzenia są ciągłe
w kolejności wejść:

| impl | selekcja |
|---|---|
| `scattered` | `Any(PPSLocalTrack_decRPId == 22)` — ocalałe rozrzucone po całym pliku |
| `contiguous` | `rdfentry_ < N` — ocalałe tworzą prefiks |

Jeśli wyjaśnienie „koszyki" z TESTU 2 jest trafne, wersja ciągła powinna czytać istotnie
mniej. Jeśli obie czytają całą kolumnę — wyjaśnienie jest błędne i trzeba je zastąpić.

Wynik do raportowania: `bytes_loop` i `read_amplification` dla obu, obok siebie.

---

## Otwarte pytanie: skąd 10 GB odczytu na `ds_l`

Do rozstrzygnięcia w kampanii, bo od tego zależy, jak czytać wszystkie wyniki o bajtach.
Zmierzone dotąd:

| plik | zdarzeń | chain-len | odczyt w pętli | amplifikacja |
|---|---|---|---|---|
| `examples/test.root` | 346 825 | 5 | 5.4 MB | 1.04 |
| `ds_x1`, `ds_x8` (Snapshot) | 346 825 / 2.8 M | 5 | 8–45 MB | 1.03 |
| `ds_m` | 2 774 600 | 5 | 44.9 MB | brak amplifikacji |
| `ds_l` | 10 935 000 | **1** | **10 215 MB** | ≈ cały plik |

Przy jednym filtrze na płaskim intie `ds_l` czyta cały plik. Co więcej, odczyt **rośnie
z liczbą wątków**: 10.2 GB przy 1 wątku, 13.6 GB przy 2, 20.4 GB przy 4. Układ pliku nie
zmienia się między tymi biegami, więc samego układu to nie wyjaśnia — zmienia się liczba
instancji `TTreeCache`.

Sprawdzone lokalnie i **nieodtworzone**: klaster większy niż cache (106 MB klaster przy 30 MB
cache) nie wywołuje amplifikacji; wyłączenie `TTreeCache` też nie zmienia odczytu; plik
„slim" z 10 gałęziami zamiast 1984 też nie. Czyli hipoteza „za mały cache na klaster" jest
osłabiona, ale nie wykluczona przy 40 kopiach.

Narzędzia w kampanii:
- `diag_io.py` — `TTreePerfStats` na czystym odczycie TTree: liczba wywołań read, bajty
  odczytane **ponad** to, o co poproszono, sweep rozmiaru `TTreeCache`,
- wykres `07b_bytes_vs_threads.png` — czy odczyt rośnie z wątkami,
- `run_benchmark.sh layout` — `ds_x8` vs `ds_x8_slim` vs `ds_x8_coarse`, każdy z cache'em
  włączonym i wyłączonym,
- `run_benchmark.sh rntuple` — te same zapytania na tych samych zdarzeniach w RNTuple, który
  nie ma ani koszyków, ani `TTreeCache`.

---

## Metryki

### Wyniki główne (deterministyczne, odporne na szum i na maszynę)

1. **Peak RSS vs rozmiar danych** — najważniejszy wykres. RDF strumieniowo → linia pozioma
   O(1). Python materializuje kolumny → linia ukośna O(N) aż do wyczerpania pamięci.
   Raportowany w dwóch wersjach, bo to konieczne: interpreter, PyROOT i NumPy zajmują ~470 MB
   *przed* jakimkolwiek odczytem, przy szczycie 474–1000 MB. Sam `peak_rss_kb` nie odróżnia
   więc implementacji strumieniowej od materializującej — dlatego rekord ma też
   `rss_baseline_kb` i `peak_rss_net_kb`.
2. **Liczba pętli zdarzeń** (TEST 2) — liczona, nie mierzona. `rdata_analysis` z 5 filtrami =
   6 przebiegów; wersja leniwa = 1; `Report()` = 1 ze statystykami.
3. **Amplifikacja odczytu** — `bytes_loop` podzielone przez `GetZipBytes()` gałęzi nazwanych
   przez zapytanie. Lepsza miara niż „procent pliku", bo nie zależy od tego, ile
   nieużywanych gałęzi akurat jest w pliku. 1.0 oznacza „przeczytane dokładnie to, o co
   poproszono".
4. **Throughput (evt/s, tracks/s) przy 1 wątku** — stosunek między implementacjami. Odporny na
   20% błędu pomiaru.
5. **Skalowanie z rozmiarem danych** — nachylenia prostych. Wszystkie implementacje O(N)
   w czasie, stała różni się o rzędy wielkości; ścieżki pythonowe dodatkowo O(N) w pamięci.
6. **Stały koszt vs pętla zdarzeń** — `wall_fixed` (setup + warmup + jit) obok `wall_loop`.
   Rozstrzyga, które „różnice między implementacjami" znikają przy dłuższym biegu.

### Wyniki pomocnicze (raportować z opisem ograniczeń)

7. **Skalowalność wątkowa** — sweep `EnableImplicitMT(N)`, obcięty do
   `min(nproc, liczba klastrów TTree / 4)` **dla użytego datasetu**. Obowiązkowo opisać
   ograniczenia, bo inaczej wykres wprowadza w błąd:
   - RDF zrównolegla po **klastrach**, nie po zdarzeniach; wątki > klastry = bezczynność
   - pomiar jest na **ciepłym cache** (dataset << RAM węzła) — świadoma decyzja metodologiczna
   - kompilacja clinga, otwarcie pliku i scalanie wyników są szeregowe
   - implementacja pythonowa nie skaluje się poza fazą `AsNumpy` (GIL) — to wynik, nie wada testu
   - `OMP_NUM_THREADS` i spółka są przypięte do 1, bo bez tego „jednowątkowe z konstrukcji"
     ścieżki pythonowe mierzyły 107–236% CPU
8. **Eksperyment kontrolny: mało vs dużo klastrów** — `ds_x8` vs `ds_x8_coarse`, **ta sama
   liczba zdarzeń**. Para o różnych rozmiarach pozwoliłaby objętości udawać klastrowanie, więc
   `run_benchmark.sh` odmawia uruchomienia porównania, jeśli liczby zdarzeń się różnią.
9. **Zimny odczyt vs ciepły cache** — `--no-cache` usuwa plik z page cache przez
   `posix_fadvise(POSIX_FADV_DONTNEED)`. Zastępuje poprzedni „pierwszy odczyt vs kolejne",
   który mierzył 0.901 / 0.894 / 0.936 s, czyli nic: plik był ciepły już przy pierwszym biegu.
10. **RNTuple vs TTree** — te same zapytania na tych samych zdarzeniach. Koszyki, klastry
    i `TTreeCache` to pojęcia TTree, więc każdy wynik o odczycie jest częściowo wynikiem
    o formacie; to kontrola mówiąca, w jakim stopniu.
11. **CPU%**, context switches, koszt kompilacji JIT (faza `jit` + `warmup`) raportowany osobno.

---

## Datasety

`examples/test.root` waży ~250 MB. Generowane przez `make_dataset.py` (`RDataFrame.Snapshot`
z jawnym `fAutoFlush`, nie `TFileMerger` — dzięki temu liczba klastrów jest parametrem,
a nie efektem ubocznym rozmiaru).

| dataset | kopii | autoflush | do czego |
|---|---|---|---|
| `ds_s` | 1 | (źródło) | kopia pliku źródłowego, LZMA:9 — tylko referencja |
| `ds_x1 … ds_x32` | 1–32 | 10 000 | seria „vs rozmiar danych"; `ds_x1` = ścieżki jednowątkowe, `ds_x8` = główny dataset |
| `ds_x8_coarse` | 8 | 250 000 | kontrola klastrowania (ta sama treść, 25× większe klastry) |
| `ds_x8_slim` | 8 | 10 000 | kontrola amplifikacji (10 gałęzi zamiast 1984) |
| `ds_x8_rntuple` | 8 | — | konwersja `ds_x8` na RNTuple |
| `ds_l` | 40 | 15 000 | duży koniec; źródło otwartego pytania o 10 GB odczytu |

**`ds_x8` jest głównym datasetem**, nie `ds_l`. 279 klastrów robi sweep 48-wątkowy legalnym,
RDF i ścieżki pythonowe mieszczą się na jednym pliku, a stałe koszty spadają do ~4% biegu.
Na `ds_l` jedna powtórka trwała na Aresie godziny i 11 z 36 biegów wyszło w timeout.

**Ścieżki jednowątkowe idą na `ds_x1`, nie na pliku źródłowym.** Dekompresja jest częścią
mierzonej pętli, a źródło to LZMA:9, podczas gdy wszystkie generowane pliki to ZSTD:5.
Puszczenie Pythona na źródle, a RDataFrame na kopii, wstawiłoby kodek do środka porównania
implementacji.

**Kompresja: ZSTD poziom 5**, nie LZMA:9 z pliku źródłowego. Zmierzone na jednej kopii:

| algorytm | czas zapisu | rozmiar |
|---|---|---|
| LZMA:9 (źródło) | 156 s | 252 MB |
| ZSTD:5 (datasety) | 70 s | 345 MB |
| LZ4:4 | 73 s | 493 MB |

Do odnotowania w opisie wyników: **dekompresja jest częścią mierzonej pętli zdarzeń**, więc
wybór algorytmu wpływa na bezwzględne liczby. Przy ZSTD mniejsza część czasu przypada na
rozpakowywanie koszyków, a większa na samo filtrowanie, niż byłoby to przy LZMA używanym
w produkcyjnym NanoAOD CMS. Porównania *między implementacjami* pozostają ważne, bo wszystkie
czytają ten sam plik; nieważne byłoby zestawianie tych czasów z pomiarami na danych LZMA.

Ustawione na sztywno w `make_all_datasets.sh`, a nie przez zmienną środowiskową — pominięcie
jej przy jednym pliku dałoby serię z mieszanymi algorytmami i unieważniło wykres. Faktyczny
algorytm każdego pliku trafia do `dataset_info.json` (`compression_algorithm`,
`compression_level`), więc da się to zweryfikować po fakcie.

**Rozmiar koszyka pozostaje decyzją ROOT-a.** `RSnapshotOptions::fBasketSize` istnieje dopiero
od ROOT 6.34 (Ares ma 6.32), a zmierzone na jednej kopii robi coś odwrotnego do nazwy:
poproszenie o koszyki 1 MiB dało koszyki 105 kB przy domyślnych 247 kB, bo ustawia alokację
początkową, a `OptimizeBaskets` potem i tak wszystko przelicza pod klaster. Faktycznym
pokrętłem jest `--autoflush`, czym różnią się `ds_x8` i `ds_x8_coarse`.

---

## Weryfikacja

1. `validate.py` — implementacje dają identyczne (1e-6) wyniki kontrolne w obrębie każdego
   testu, włącznie z `uproot` i `--filter-style callable`.
2. `validate.py` — `assignRegion` C++ vs `diamond_geometry.assign_region` na 100k punktów,
   zero rozbieżności. Sprawdzane **przed** porównaniem implementacji: przy błędnej
   transkrypcji geometrii wszystkie mogą się zgadzać i być wspólnie błędne.
3. TEST 2: wszystkie ścieżki zwracają tę samą końcową liczbę zdarzeń dla każdego
   `--chain-len`; `rdf-eager` i `rdf-report` zwracają te same liczności pośrednie.
4. TEST 2: krótkie spięcie predykatów (`--mode vector-shortcircuit`) i kolejność filtrów
   (`--chain-order`) nie mogą zmienić odpowiedzi — zmieniają tylko ilość wykonanej pracy.
5. TEST 3: `--impl jit` na 1 vs N wątkach — identyczne wyniki kontrolne (thread-safety kernela).
6. Liczba klastrów w `results/dataset_info.json` ≥ 4× maksymalna liczba wątków w sweepie,
   sprawdzana **dla użytego datasetu**. Każdy dataset biorący udział w pomiarze musi mieć
   wpis w `dataset_info.json` — bez tego limit wątków i adnotacje na wykresach brałyby liczby
   z innego pliku.
7. Ta sama wersja ROOT i ten sam dataset na obu maszynach, inaczej porównanie międzymaszynowe
   jest nieważne. Rekordy noszą `schema_version`; `plot_results.py` odrzuca starsze, bo część
   pól zmieniła znaczenie i nie wolno ich uśredniać razem.
8. Każdy pojedynczy bieg ≤ 5 min (`timeout 300`). Biegi, które przekroczyły limit, są
   **rysowane jako dolne ograniczenia**, nie pomijane: ścieżka, która nie kończy w 300 s, to
   wynik o implementacji, a nie brak danych.

---

## Poza zakresem

- warianty pandas; wielowęzłowe MPI/Dask
- stary `apply_diamond_efficiency_hybrid` (AsNumpy + pętla + `unordered_map`) — usunięty
  z produkcji w tym samym refaktorze, nie jest benchmarkowany
- generyczny `apply_corrections_hybrid` — zostaje pętlą Pythona, bo obsługuje dowolny schemat
  correctionlib o nieznanych z góry `input_names`. To granica zastosowalności optymalizacji,
  warta opisania w pracy, ale nie ruszamy jej.
