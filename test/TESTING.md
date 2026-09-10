# Plan testów wydajnościowych

Trzy niezależne mikrobenchmarki operacji z notebooka, uporządkowane od najprostszej do
najbardziej złożonej. Każdy porównuje skompilowaną ścieżkę RDataFrame z implementacją
pythonową.

Stała konfiguracja: **rp_id = 22** (pot typu box, ramię 45, 3 regiony).

| test | operacja | dlaczego w tej kolejności |
|---|---|---|
| TEST 1 | jeden filtr | najprostsza operacja, jedna gałąź, punkt odniesienia |
| TEST 2 | łańcuch filtrów | kompozycja predykatów, wiele gałęzi, eager vs lazy |
| TEST 3 | dopisanie efficiency | dodanie nowych danych do rekordów, obliczenia per track |

---

## TEST 1 — pojedynczy filtr (`decRPId == 22`)

Selekcja zdarzeń zawierających przynajmniej jeden track w danym pocie.

| impl | co robi |
|---|---|
| `rdf` | `df.Filter("Any(PPSLocalTrack_decRPId == 22)")` + `Count()` |
| `python --mode vector` | `AsNumpy(["PPSLocalTrack_decRPId"])`, spłaszczenie jagged, maska `flat == 22`, `np.bincount` |
| `python --mode loop` | `sum(1 for a in arrays if 22 in a)` |

- **Wynik kontrolny**: liczba zdarzeń przechodzących filtr.
- **Czego dowodzi**: RDF czyta jedną gałąź strumieniowo i nie materializuje nic (RSS ~ O(1));
  Python musi wciągnąć całą kolumnę jagged do RAM (RSS ~ O(N)) zanim cokolwiek policzy.

Selektywność kolumnowa nie jest mierzona tutaj — robi to TEST 2 przez sweep długości
łańcucha, naturalnie i wiarygodniej.

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

**Cztery punkty pomiarowe:**

| impl | co robi | co mierzy |
|---|---|---|
| `rdf-lazy` | cały łańcuch `Filter`, jedno `Count()` na końcu | 1 pętla zdarzeń |
| `rdf-eager` | `Count()` na starcie i po każdym filtrze — dokładnie to, co robi `rdata_analysis` | `chain_len + 1` pętli |
| `rdf-report` | łańcuch + `Report()` na końcu | liczności wszystkich filtrów w jednej pętli |
| `python` | `AsNumpy` potrzebnych kolumn, potem maski sekwencyjnie; całe filtrowanie po stronie Pythona | koszt po stronie interpretera |

Wszystkie cztery dają identyczne liczności pośrednie. Różni je liczba przebiegów i odczyt:

| chain-len | `rdf-lazy` | `rdf-report` | `rdf-eager` | `python` |
|---|---|---|---|---|
| 1 | 0.21 MB / 1 pętla | 0.21 MB / 1 | 0.21 MB / 2 | 0.21 MB / 1 |
| 2 | 0.99 / 1 | 0.99 / 1 | 1.20 / 3 | 0.99 / 1 |
| 3 | 1.47 / 1 | 1.47 / 1 | 2.66 / 4 | 1.47 / 1 |
| 4 | 1.47 / 1 | 1.47 / 1 | 4.13 / 5 | 1.47 / 1 |
| 5 | 5.40 / 1 | 5.40 / 1 | **9.53 / 6** | 5.40 / 1 |

- **Czego dowodzi**:
  1. `rdf-eager` vs `rdf-lazy` — koszt wypisywania statystyk po każdym kroku. Przy pięciu
     filtrach to 6 przebiegów zamiast jednego i **1.8x więcej odczytanych bajtów**: każdy
     kolejny przebieg czyta swoje kolumny od nowa.
  2. `rdf-report` daje te same statystyki w jednej pętli i przy tym samym odczycie co wersja
     leniwa — gotowa rekomendacja zmiany w `rdata_analysis`.
  3. **Selektywność kolumnowa**: z pliku 240 MB o 1984 gałęziach pełny łańcuch odczytuje
     5.4 MB — **2.2%**. Odczyt nie zmienia się między krokiem 3 a 4, bo krok 4 nie dokłada
     kolumny, choć odrzuca kolejne 15 tys. zdarzeń.
  4. Pamięć Pythona rośnie z liczbą materializowanych kolumn, RDF nie.

> **Zmierzone, wbrew pierwotnej hipotezie:** `rdf-lazy` odczytuje *tyle samo* bajtów co ścieżka
> pythonowa na każdej długości łańcucha. Zakładałam, że późniejsze gałęzie będą czytane tylko
> dla zdarzeń, które dotarły do danego węzła, więc odczyt będzie rość subliniowo. Tak nie jest:
> ROOT czyta całe **koszyki**, a przefiltrowane zdarzenia są rozrzucone po wszystkich koszykach
> danej gałęzi, więc każdy i tak trzeba zdekompresować. Krótkie spięcie predykatów oszczędza
> CPU, nie I/O. Odczyt stałby się subliniowy dopiero przy selekcji ciągłej w kolejności
> zdarzeń (np. po numerze runu).

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

Jeden tryb geometrii: **`rotated`**. Wariant `bbox` (osiowe zakresy x/y) odrzucony — geometria
pota faktycznie jest obrócona, więc wersja bez rotacji nie jest alternatywą, tylko błędnym
obliczeniem.

- **Wyniki kontrolne**: suma efficiency po wszystkich trackach, liczba tracków z eff > 0.

> Bez akcji terminalnej RDF jest leniwy i nie policzy nic. Każdy pomiar kończy się identyczną
> redukcją we wszystkich implementacjach.

---

## Metryki

### Wyniki główne (deterministyczne, odporne na szum i na maszynę)

1. **Peak RSS vs rozmiar danych** — najważniejszy wykres. RDF strumieniowo → linia pozioma
   O(1). Python materializuje kolumny → linia ukośna O(N) aż do wyczerpania pamięci. Nie
   zależy od cache, obciążenia klastra ani turbo CPU. Pokazuje rozmiar, przy którym podejście
   pythonowe **przestaje działać**, a nie tylko zwalnia.
2. **Liczba pętli zdarzeń** (TEST 2) — liczona, nie mierzona. `rdata_analysis` z 5 filtrami =
   6 przebiegów; wersja leniwa = 1; `Report()` = 1 ze statystykami.
3. **Bajty odczytu vs liczba dotkniętych gałęzi** (TEST 2) — z `TFile::GetFileBytesRead()`.
   Łańcuch trzech filtrów czyta 5.4 MB z pliku 240 MB o 1984 gałęziach. Identycznie w obu
   implementacjach: selekcja działa na poziomie *kolumn*, nie *wierszy* (patrz uwaga
   przy TEŚCIE 2).
4. **Throughput (evt/s, tracks/s) przy 1 wątku** — stosunek między implementacjami. Odporny na
   20% błędu pomiaru. To właściwa forma porównania, bo implementacje biegną na **różnych**
   rozmiarach danych.
5. **Skalowanie z rozmiarem danych** — nachylenia prostych. Obie implementacje O(N) w czasie,
   stała różni się o rzędy wielkości; Python dodatkowo O(N) w pamięci.

### Wyniki pomocnicze (raportować z opisem ograniczeń)

6. **Skalowalność wątkowa** — sweep `EnableImplicitMT(N)`, obcięty do
   `min(nproc, liczba klastrów TTree)`. Obowiązkowo opisać ograniczenia, bo inaczej wykres
   wprowadza w błąd:
   - RDF zrównolegla po **klastrach**, nie po zdarzeniach; wątki > klastry = bezczynność
   - pomiar jest na **ciepłym cache** (dataset << RAM węzła) — świadoma decyzja metodologiczna,
     usuwa dysk jako zmienną zakłócającą przy porównaniu implementacji po stronie CPU
   - kompilacja clinga, otwarcie pliku i scalanie wyników są szeregowe — przy biegu 60 s
     ogranicza speedup do rzędu 20–30× niezależnie od liczby rdzeni
   - implementacja pythonowa nie skaluje się poza fazą `AsNumpy` (GIL) — to wynik, nie wada testu
7. **Eksperyment kontrolny: mało vs dużo klastrów** na tym samym pliku. Dowodzi, że plateau
   bierze się z klastrów, a nie z kodu.
8. **Pierwszy odczyt vs kolejne** — tani proxy kosztu I/O (zastępuje odrzucony eksperyment
   z zimnym cache'em, który wymagałby ~320 GB danych).
9. **CPU%**, context switches, koszt kompilacji JIT raportowany osobno.

---

## Datasety

`examples/test.root` waży ~250 MB. Generowane przez `make_dataset.py` (`RDataFrame.Snapshot`
z jawnym `fAutoFlush`, nie `TFileMerger` — dzięki temu liczba klastrów jest parametrem,
a nie efektem ubocznym rozmiaru).

| dataset | kopii | rozmiar | do czego |
|---|---|---|---|
| S | 1 | 250 MB | `python --mode loop`, `correctionlib` per track |
| M | 8 | 2 GB | `python --mode vector`, walidacja krzyżowa |
| L | 40 | 10 GB | `jit`, główny punkt, sweep wątków (Ares) |
| XL | 100 | 25 GB | `jit`, sweep wątków (Helios) |
| seria | 1,2,4,8,16,32,64 | 0.25–16 GB | wykresy „vs rozmiar danych" |

Razem ~50 GB scratcha.

**Różne rozmiary dla różnych implementacji są zamierzone.** Porównanie idzie wyłącznie przez
throughput (evt/s), nigdy przez surowy wall time — inaczej Python nie zmieściłby się w limicie
3 minut na datasecie L. Rozmiary to oszacowanie przy założeniu 50–300 MB/s/rdzeń dekompresji;
skorygować po pierwszym pomiarze tak, żeby `jit` na 1 wątku trwał ≥ 60 s.

---

## Weryfikacja

1. `run_benchmark.sh --validate` — implementacje dają identyczne (1e-6) wyniki kontrolne
   w obrębie każdego testu.
2. `validate.py` — `assignRegion` C++ vs `diamond_geometry.assign_region` na 100k punktów,
   zero rozbieżności.
3. TEST 2: wszystkie cztery ścieżki zwracają tę samą końcową liczbę zdarzeń dla każdego
   `--chain-len`; `rdf-eager` i `rdf-report` zwracają te same liczności pośrednie.
4. TEST 2: bajty odczytu przy `--chain-len 3` w RDF muszą być **mniejsze** niż suma
   `GetZipBytes()` trzech gałęzi (dowód krótkiego spięcia predykatów); w Pythonie
   w przybliżeniu **równe** tej sumie.
5. TEST 3: `--impl jit` na 1 vs N wątkach — identyczne wyniki kontrolne (thread-safety kernela).
6. Liczba klastrów w `results/dataset_info.json` ≥ 4× maksymalna liczba wątków w sweepie.
   Jeśli nie — plateau na wykresie skalowania jest artefaktem datasetu, nie właściwością kodu.
7. Ta sama wersja ROOT i ten sam dataset na obu maszynach, inaczej porównanie międzymaszynowe
   jest nieważne.
8. Każdy pojedynczy bieg ≤ 3 min (`timeout 300`).

---

## Poza zakresem

- warianty pandas, awkward, uproot; wielowęzłowe MPI/Dask
- stary `apply_diamond_efficiency_hybrid` (AsNumpy + pętla + `unordered_map`) — usunięty
  z produkcji w tym samym refaktorze, nie jest benchmarkowany
- generyczny `apply_corrections_hybrid` — zostaje pętlą Pythona, bo obsługuje dowolny schemat
  correctionlib o nieznanych z góry `input_names`. To granica zastosowalności optymalizacji,
  warta opisania w pracy, ale nie ruszamy jej.
