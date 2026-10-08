# Benchmark: RDataFrame vs Python na NanoAOD

Zostały tylko skrypty trzech ścieżek: ostatecznej kampanii na Heliosie (jedno zadanie
`slurm_final.sbatch` na `plgrid-now`: łańcuch 11 filtrów na ~1 TB sztucznych pełnych plików,
~1 TB Run 2 Open Data i Run 3 z `data3-full`, plus RDF i uproot na całym węźle na Run 3), pojedynczych
zadań Run 3 (`run3_helios.sh`) i kampanii ogólnej
`slurm_benchmark.sbatch` na plikach sztucznych (`DATASET=synthetic` i `DATASET=big`), z której
pochodzi porównanie RDF / uproot / pętla w Pythonie (seria rozmiarów `size`, `sizepy`, wykresy
08 i 13). Pobieranie danych (EOS, DAS, Open Data), budowanie list i zakończone kampanie (Helios
H1–H4, slim11, real vs synthetic na łańcuchu 5 filtrów, memtrace) są w
[`archive/`](archive/README.md), razem z ich opisami; nic z poniższego ich nie woła.

## Co się uruchamia

Ręcznie uruchamia się tylko pliki z kolumny „uruchamiasz”, resztę wołają one same.

| ścieżka | uruchamiasz | to woła |
|---|---|---|
| ostateczna kampania (Helios, `plgrid-now`) | `sbatch test/slurm_final.sbatch`: bramka Run 2, F, R, J1, J3 po kolei | `check_chain11.py`; `slurm_benchmark.sbatch` (F, R); `slurm_run3.sbatch` (J1, J3) |
| pojedyncze zadania Run 3 (Helios, `plgrid`) | `run3_helios.sh`: J1 strong, J2 weak; J3, J4 opcjonalnie | `slurm_run3.sbatch` → `validate.py`, `dataset_json.py`, `bench_chain.py`, `run_benchmark.sh` |
| pliki sztuczne, `DATASET=big` (Ares, Helios) | `sbatch slurm_benchmark.sbatch` | `run_all.sh` → `validate.py`, `run_benchmark.sh` → `plot_results.py` |
| kopie dla `DATASET=big` (raz) | `make_bigset.sh` | — |
| wykresy i tabele (lokalnie) | `plot_results.py`; porównanie zbiorów: `plot_real_vs_synthetic.py` | — |

`run_benchmark.sh` woła pojedyncze pomiary `bench_filter.py`, `bench_chain.py`,
`bench_efficiency.py` i `bench_pool.py`, a dla T6 `make_slim.py`. Wszystkie importują
`bench_common.py`, `bench_spec.py` i `impl_*.py`.

## Pliki

| plik | rola |
|---|---|
| `run3_helios.sh`, `slurm_run3.sbatch` | kampania Run 3: zadania J1–J4 (`JOB=`); domyślnie J1 i J2, niezależnie od siebie, J3 i J4 opcjonalnie (`afterany`) |
| `slurm_final.sbatch` | ostateczna kampania jako jedno zadanie na `plgrid-now` (12 h): kroki `gate`, `F`, `R`, `J1`, `J3` (`STEPS=`), wznawialne, `DRY_RUN=1` wypisuje kroki |
| `check_chain11.py` | przed kampanią na prawdziwych plikach: typy 10 kolumn łańcucha w każdym pliku i liczba zdarzeń po każdym z 11 filtrów, dla okresu `--period` |
| `plot_real_vs_synthetic.py` | porównanie zbiorów `--set DIR:TEST:LABEL`: rysunek pełnych plików (czas, przyspieszenie, RSS) i tabela zbiorów (`sets_summary.{csv,tex}`) |
| `slurm_benchmark.sbatch` | kampania ogólna: zadanie na całym węźle (`--exclusive`), Ares albo Helios; `DATASET_JSON_INPUT` pisze `dataset.json` |
| `run_all.sh` | sprawdza środowisko i Git LFS, uruchamia walidację, potem kampanię |
| `validate.py` | zgodność wszystkich implementacji, geometria C++ vs Python, 1 vs N wątków |
| `run_benchmark.sh` | kampania T1/T2/T4/T5/T6/T2S i testy `*11`, `size`, `sizepy`, zbiera `raw.jsonl`, na końcu rysuje wykresy |
| `dataset_json.py` | `dataset.json` w katalogu wyników: pliki, zdarzenia, gałęzie, klastry i koszyki na plik, kodek |
| `make_slim.py` | kopia wejścia T1 z samymi używanymi kolumnami (plik albo lista) dla T6 |
| `make_bigset.sh` | tylko kopiuje: `ds_1.root` … `ds_96.root` obok `ds_x32.root`, czyli wejście `DATASET=big` |
| `bench_filter.py`, `bench_chain.py`, `bench_efficiency.py` | pojedynczy pomiar (TEST 1–3) |
| `bench_pool.py` | łańcuch na całym węźle bez ImplicitMT: uproot (`uproot-pool`) albo AsNumpy (`python-pool`) w puli procesów, plik na zadanie |
| `bench_common.py` | parser argumentów, fazy czasu, liczniki bajtów i RSS (z procesami potomnymi), rekord `BENCH` |
| `bench_spec.py` | łańcuchy, kolumny, cięcia i listy wejść, bez ROOT-a (dla procesów puli uproot) |
| `impl_rdf.py`, `impl_python.py`, `impl_uproot.py` | implementacje mierzonych operacji |
| `plot_results.py` | `raw.jsonl` → `bench.csv` + wykresy i tabele (lokalnie, tylko matplotlib) |
| `environment.yml` | env `pps-bench` (ROOT, correctionlib, uproot, awkward, matplotlib) |

## Dane

Każde wejście benchmarku (`--input`) to plik `.root` albo lista `.txt` (jedna ścieżka na linię;
ścieżki względne liczone od katalogu listy). `run_benchmark.sh` przed startem sprawdza, że
istnieje każde wejście i każdy plik z każdej listy.

| rola | `DATASET=synthetic` | `DATASET=real` | `DATASET=big` |
|---|---|---|---|
| T1 (`DS_CORE`) | `ds_x32.root` | `core.txt` | `lists/core.txt` (96 kopii, ~1 TB) |
| T2 (`WEAK_PATTERN`) | `ds_x%s.root`, N = 1…32 | `weak_%s.txt`, N = 1…48 | `lists/weak_%s.txt`, 2N kopii |
| T4, T5 (`DS_IMPL`) | `ds_x32.root` | `impl.txt` (~11 mln zdarzeń) | `lists/impl.txt` (9 kopii, ~98 GB); T5 nie biegnie |
| `size`, `sizepy` (`SIZE_PATTERN`) | — | — | `lists/size_%s.txt`, N = 1, 2, 4, 6, 8, 9 kopii |
| T6 (`DS_SLIM`) | `ds_x32_slim.root` | `core_slim.txt` + `slim/` | domyślnie nie jest mierzony |

Przy `DATASET=big` listy w `$DATA_DIR/lists/` pisze sam `run_benchmark.sh` na starcie kampanii,
z pierwszych N plików `ds_1.root`, `ds_2.root`, … (wpisy `../ds_N.root`).

### Syntetyczne: `ds_xN`

Seria `ds_xN` (N kopii `examples/test.root`, ZSTD:5, autoflush 10 000) musi już leżeć
w `$DATA_DIR`.

| plik | zdarzeń | klastrów | GB | rola |
|---|---:|---:|---:|---|
| `ds_x1` | 346 825 | 36 | 0.34 | T2 przy 1 wątku |
| `ds_x2` | 693 650 | 71 | 0.68 | T2 przy 2 wątkach |
| `ds_x4` | 1 387 300 | 140 | 1.35 | T2 przy 4 wątkach |
| `ds_x8` | 2 774 600 | 279 | 2.71 | T2 przy 8 wątkach |
| `ds_x16` | 5 549 200 | 556 | 5.41 | T2 przy 16 wątkach |
| `ds_x32` | 11 098 400 | 1111 | 10.84 | T2 przy 32 wątkach **oraz całe T1, T4 i T5** |
| `ds_x32_slim` | 11 098 400 | ~1110 | — | T6; tworzony automatycznie przy pierwszym uruchomieniu |

Klastrów na wątek jest w serii praktycznie stała liczba (36.0 … 34.7), a RDataFrame dzieli pracę
po klastrach, więc para (N wątków, `ds_xN`) daje uczciwe skalowanie słabe.

`ds_x32_slim` to `Snapshot` z `ds_x32` tylko z gałęziami, które czytają testy (`nPPSLocalTrack`,
`PPSLocalTrack_{decRPId,rpType,x,y}`, `Proton_singleRP_xi`; plus gałęzie rozmiaru, które
Snapshot dopisuje dla kolumn tablicowych) zamiast 1984. `make_slim.py` przenosi kodek pliku
źródłowego i jego średni rozmiar klastra, a zapis jest jednowątkowy, więc liczba klastrów się
zgadza. Sprawdza też, że liczba zdarzeń jest identyczna. Dla listy odchudza każdy plik osobno
do `slim/` obok listy wyjściowej, a samą listę zapisuje na końcu: jeśli istnieje, jest kompletna.

## Ostateczna kampania (Helios, jedno zadanie)

Wszystko, czego praca jeszcze potrzebuje z Heliosa, w jednym zadaniu `slurm_final.sbatch`
na partycji `plgrid-now`, krok po kroku na tym samym węźle, więc żaden pomiar nie dzieli Lustre
z innym. Jedno zadanie, bo QoS `plgrid-now` pozwala na jedno zadanie użytkownika naraz, licząc
oczekujące (`MaxSubmitPU=1`), więc łańcucha z zależnościami nie da się nawet wysłać. Reszta
ograniczeń to przydział zadania: jeden węzeł (192 rdzenie), 384 000 MB, `MaxTime=12:00:00`.

| krok | co | katalog wyników na `$SCRATCH/bench` | szacunek |
|---|---|---|---|
| `bigset` | `make_bigset.sh`: brakujące kopie `ds_1.root` … `ds_96.root` z `data/ds_x32.root` | `data/` | 0,5–1 h, gdy brak wszystkich; sekundy, gdy są |
| `gate` | `check_chain11.py --period 2016` na każdym pliku Run 2, 96 procesów | `run2_chain11_gate.{txt,status}`, `run2_chain11.csv` | ~5 min |
| `F` | `strong11`, sztuczne pełne pliki (`DATASET=big`, 96 kopii `ds_x32`) | `results-helios-full11-1tb` | 1,5–2 h |
| `R` | `strong11`, Run 2 Open Data, `--period 2016`; tylko gdy bramka dała 0 | `results-helios-run2-chain11-1tb` | 1–1,5 h |
| `J1` | `strong11`, Run 3 `core.txt`, `--period run3` | `results-helios-run3-chain11` | 2,5–3 h |
| `J3` | `node11`: RDF na 192 wątkach i `uproot-pool` na 192 procesach, po 3 biegi | `results-helios-run3-node` | ~0,5 h |

F, R i J1: 1–192 wątki raz, 80–192 trzy razy (r1–r3). Razem ~6–7,5 h z `validate.py` przed
każdym krokiem pomiarowym. J2 (weak na Run 3) i J4 (Python w puli) nie wchodzą: weak jest
w pracy tylko na slim, a pula Pythona na całym zbiorze grozi brakiem pamięci i daje wynik,
który da się przewidzieć z bloku A.

- Błąd jednego kroku nie zatrzymuje następnych; na końcu logu jest podsumowanie kodów wyjścia.
- Wszystko dopisuje z `RESUME=1`, a bramka zapisuje swój kod wyjścia, więc to samo zadanie
  wysłane jeszcze raz (np. po 12 h) robi tylko brakujące biegi. Bramkę od nowa: usunąć
  `run2_chain11_gate.status`. Zapisaną bramkę, po której łańcuch nie zostawił nic
  (`0 left after the chain`), krok `gate` liczy od nowa sam.
- J1 sam odsuwa katalog `results-helios-run3-chain11`, jeśli ma rekordy z innym okresem niż
  `run3` (stare cięcia), jako `...-oldcuts-<data>`. R tak samo odsuwa
  `results-helios-run2-chain11-1tb` z rekordami `events_passed: 0` jako `...-nopass-<data>`.
- Bramka: kod 3 to plik, którego nie da się przeczytać przez łańcuch (np. bez którejś z 10
  gałęzi), kod 2 to kolumna z dwoma typami, kod 4 to łańcuch, po którym w całym zbiorze nie
  zostaje żadne zdarzenie. Wtedy R jest pomijane i wracamy do decyzji. Kod 4 to nie formalność:
  kosze wszystkich 10 gałęzi i tak są czytane z dysku, ale filtry za pierwszym pustym nie są
  liczone, a ich gałęzie rozpakowywane, więc pętla ma mniej pracy CPU niż na danych, które
  przechodzą (na pliku 2016 te same 0,75% pliku odczytu, ale o ~35% mniej CPU). Cięcia 2016:
  „Pełne pliki, łańcuch 11”.

Krok po kroku:

1. Laptop: wysłać kod (`git push`). `doc/` i pliki `.root` są ignorowane.
2. Helios, login: pobrać kod i sprawdzić, że nic innego nie biegnie ani nie czeka. Starsze
   zadania benchmarku (np. na `plgrid`) skasować albo odczekać, bo dzieliłyby Lustre:

   ```bash
   cd $SCRATCH/bench/nanoaod-pps-tools && git pull
   squeue -u $USER
   ```

3. Dane na scratchu (czyszczony po ~30 dniach):

   ```bash
   hpc-fs
   ls -l $SCRATCH/bench/data/ds_x32.root $SCRATCH/bench/data/ds_1.root $SCRATCH/bench/data/ds_96.root \
         $SCRATCH/bench/data2/core.txt $SCRATCH/bench/data2/local.csv
   head -1 $SCRATCH/bench/data3-full/READY   # files 2454
   f=$(head -1 $SCRATCH/bench/data3-full/core.txt); ls -lL "$f"   # plik danych, nie tylko lista
   ```

   Run 3 jest w `data3-full` (ten sam zbiór co wszystkie dotąd biegi J1, dawniej przez
   dowiązanie `data3-snap`). W `data3-full` są listy, `READY` i inwentaryzacja; same pliki są pod
   `data3-full/data`, dowiązaniem do `data3/data`. Brak kopii
   `ds_N.root`: robi je krok `bigset` w tym samym zadaniu, wystarczy `ds_x32.root` i miejsce na
   ~1 TB (najpierw `hpc-fs`, czy kwota to pomieści). Brak Open
   Data: `opendata_helios.sh --fetch-only`, który trzeba najpierw przenieść z `archive/` razem
   z plikami, które woła (`archive/README.md`, na górze).

4. Podgląd i wysłanie (z katalogu repo, tam trafią logi):

   ```bash
   DRY_RUN=1 bash test/slurm_final.sbatch
   sbatch test/slurm_final.sbatch
   ```

   Na loginie `DRY_RUN=1` wypisuje też brakujące wejścia kroków. Zadanie z brakującym wejściem
   kończy się od razu, zanim cokolwiek zmierzy.

5. Śledzenie: `squeue -u $USER`, `tail -f bench-final-<id>.out`. Do końca zadania nie robić
   `git pull`: kroki wołają skrypty z repo w chwili startu.
6. Brak czasu albo jeden krok do powtórzenia: to samo jeszcze raz, ewentualnie tylko część:

   ```bash
   sbatch test/slurm_final.sbatch
   sbatch --export=ALL,STEPS="J1 J3" test/slurm_final.sbatch
   ```

7. Laptop: zabrać wyniki (polecenia w `results/README.md`) i zrobić rysunki: porównanie zbiorów
   `plot_real_vs_synthetic.py` i wykres 17 z `plot_results.py` na `results/run3/node`.

## Kampania Run 3 (Helios)

Pojedyncze zadania na `plgrid`; ostateczne J1 i J3 biegną w `slurm_final.sbatch`.

Tylko łańcuch 11 filtrów (10 gałęzi), tylko pełne oryginalne pliki z `data3-full`, czytane z
Lustre na zimno. Listy (`core.txt`, `weak_N.txt`, `impl.txt`, `local.csv`, `sets.json`,
`READY`) leżą w `$SCRATCH/bench/data3-full`, pliki pod `data3-full/data`; skrypty, które je pobrały i zbudowały, są w `archive/`
(„Run 3 z EOS przez lxplus”). Osobne zadania `slurm_run3.sbatch`, każde na całym węźle. Domyślnie tylko skalowanie,
J1 i J2: żadne nie czeka na drugie, więc każde stoi w kolejce samo i mogą biec jednocześnie na
dwóch węzłach. Cache stron jest osobny na każdym węźle, ale Lustre wspólny, więc nakładanie się
J1 i J2 w czasie trzeba podać przy wynikach. J3 i J4 startują po końcu wszystkich wcześniej
wysłanych (`afterany`); J3 wchodzi do ostatecznej kampanii, J4 nie:

| zadanie | co | katalog wyników |
|---|---|---|
| J1 | `strong11` na `core.txt`, 1–192 wątki, 80–192 jeszcze dwa razy (r2, r3); najpierw próba 1 wątku na `impl.txt`, z niej `RUN_TIMEOUT` (3 × szacunek t1) | `results-helios-run3-chain11` |
| J2 | `weak11`: `weak_N` na N wątkach, N = 1, 2, 4, 8, 16, 32, 48, 64, 96 | `results-helios-run3-chain11-weak` |
| J3 | `node11`: RDF na 192 wątkach (kontrola) i `uproot-pool` na 192 procesach, cały zbiór, po `REPEATS_NODE` (3) biegów | `results-helios-run3-node` |
| J4 (opcja) | `node11`: `python-pool` na 192 procesach, cały zbiór | `results-helios-run3-node` |

```bash
cd $SCRATCH/bench/nanoaod-pps-tools
bash test/run3_helios.sh --dry-run        # podgląd
bash test/run3_helios.sh                  # J1 i J2 (5 h i 2 h)
bash test/run3_helios.sh --from J1        # J1-J4
bash test/run3_helios.sh --only J3        # jedno zadanie
TIME_J1=12:00:00 bash test/run3_helios.sh --only J1
```

- **Pule (`bench_pool.py`):** uproot i AsNumpy nie zrównoleglają pętli i trzymają czytane
  kolumny w pamięci, więc na całym węźle biegną tak, jak używa się ich w praktyce: N procesów,
  jeden plik na zadanie, pliki od największego. Proces `uproot-pool` nie importuje ROOT-a.
  `setup` to start procesów i import bibliotek (do bariery), `loop` to wszystkie pliki.
  `cpu_loop` zawiera CPU procesów, `bytes_loop` i `io_*_loop` to ich sumy, a
  `peak_rss_tree_kb` to szczyt sumy RSS rodzica i procesów z przebiegu `rss_*.csv` (próbnik
  liczy całe drzewo procesów). Zabity proces (np. przez OOM) kończy bieg jako `failed`,
  zamiast go zawiesić.
- **Wykres 17** (`17_whole_node.png`): czas całkowity, CPU-h w pętli i szczytowy RSS wszystkich
  procesów dla RDF / uproot / Python. `plot_results.py` sprawdza też, że wszystkie dają tę samą
  liczbę zdarzeń.
- **Wznawianie:** każde zadanie biegnie z `RESUME=1`, więc ponownie wysłane dokłada tylko to,
  czego nie ma jako `ok`. `FRESH=1` odsuwa istniejący katalog wyników.
- **Po każdym zadaniu:** skopiować katalog wyników do `results/run3/` (J1 → `chain11/`,
  J2 → `chain11-weak/`, J3/J4 → `node/`), bo scratch jest czyszczony.

### Cięcia Run 3 i nowe J1, J2

Pierwsze J1 i J2 biegły z cięciami 2026, czyli z próbki `examples/test.root` (run 396727):
RP 22, pary 23|123 i 3|103. Na erach Run2024C–Run2026D przepuszczają 10,8%, a w kilku prawie
nic (w plikach z `READY`: 2026C 165 z 1,28 mln, 2026D 0). RP 22 ma 16–24% zdarzeń w 2024C–E,
0,9% w 2024F, 2–8% w 2025 i 0,01–0,4% w 2026; `multi_rp_idx` ucina 97% w 2024F i 2026B,
`theta_y` 99,4% w 2026D. Leżą w
`results/archive/run3-cuts2026/`. Run 3 dostaje własny okres w `bench_spec.PERIODS`, tak jak
2016, i całe J1, J2 od nowa.

Cięcia Run 3 (`PERIODS["run3"]`, `slurm_run3.sbatch` daje je domyślnie przez
`CHAIN_ARGS="--period run3"`) wybierają na pikselach: w plikach 2024–2026 (np. run 401844)
diamenty mają ślady w < 0,5% zdarzeń, a protony multi-RP w 3%. Zamiast diamentu typ 4 (piksel),
zamiast RP 22 RP 23, a cztery cięcia na śladach odwrócone: ślad poza protonem multi-RP
(`multiRPProtonIdx == -1`), ślad w protonie single-RP (`singleRPProtonIdx >= 0`), ślad bez
pomiaru czasu (`time == 0`, `timeUnc == 0`). Na run 401844 zostaje 60% zdarzeń (cięcia 2026:
0,4%); `validate.py` porównuje oba okresy w RDF, uproot i Pythonie.

J1 od nowa biegnie w `slurm_final.sbatch` (krok `J1`), z r2 i r3 przy 80–192 wątkach, które
`slurm_run3.sbatch` daje domyślnie (`STRONG11_R2_THREADS=""` wyłącza). Szacunek: t1 ~1 h, cały
przebieg z powtórkami ~2,5–3 h. J2 z cięciami Run 3 nie jest planowane.

## Pełne pliki, łańcuch 11 (Helios)

Ten sam łańcuch co Run 3 i slim (11 filtrów, 10 gałęzi, `strong11`) na całym zbiorze pełnych
plików ~1 TB naraz, czytanym z Lustre na zimno. Pliki mają ~1 TB, a pętla czyta z nich kilka
procent; slim (`results/synthetic-slim`) to 1,5 TB czytane w całości. Kroki F i R
`slurm_final.sbatch` (ostateczna kampania, wyżej), każdy przez `slurm_benchmark.sbatch`:

| zadanie | dane | co | katalog wyników |
|---|---|---|---|
| F | `DATASET=big`, `$SCRATCH/bench/data`: 96 kopii `ds_x32` (`lists/core.txt`), 1,07 mld zdarzeń, 1,04 TB | `strong11`, 1–192 wątki, 80–192 trzy razy (r1–r3) | `results-helios-full11-1tb` |
| R | `DATASET=real`, `$SCRATCH/bench/data2`: Run 2 Open Data `core.txt`, 653 pliki, 1,05 mld zdarzeń, 1,04 TB | to samo z `CHAIN_ARGS="--period 2016"` | `results-helios-run2-chain11-1tb` |

R idzie tylko po bramce `check_chain11.py` (krok `gate`), z `RUN_TIMEOUT=7200` jak F. Dane,
bramka i kody wyjścia: „Ostateczna kampania”. Po zadaniu skopiować wyniki do
`results/full-chain11/{artificial-1tb,run2-1tb}` i uruchomić porównanie (polecenie
w `results/README.md`).

### Cięcia 2016 i nowe R

Pierwsze R (8 października 2026) biegło z czterema cięciami na śladach z 2026 i nie przepuściło
żadnego zdarzenia: w 2016 PPS miał tylko detektory paskowe (`rpType 3`, pary 2|3 i 102|103),
każdy ślad należy do protonu single-RP, a żaden nie ma pomiaru czasu. `single_rp_idx == -1`
i `time != 0` odrzucały więc wszystko. `PERIODS["2016"]` zostawia cięcie multi-RP i odwraca
pozostałe trzy, jak Run 3: ślad w protonie multi-RP (`multiRPProtonIdx >= 0`), ślad w protonie
single-RP (`singleRPProtonIdx >= 0`), ślad bez czasu (`time == 0`, `timeUnc == 0`). Na pliku
`2A2D52E2-CD96-BD4C-8D60-4BC274FA8ED5.root` (102 941 zdarzeń):

| all | theta_y | multi_proton | multi_rp_idx | single_rp_idx … pps | double_arm | strip | rp_id 3 | xi |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 102 941 | 47 850 | 37 899 | 37 334 | 37 334 | 7 227 | 7 227 | 6 496 | 5 427 (5,3%) |

Ślad poza protonem multi-RP (jak w Run 3) zostawiłby 1,7%. Stare wyniki leżą lokalnie jako
`results-helios-run2-chain11-1tb-nopass` i nie wchodzą do pracy. Powtórka (krok `gate` liczy
się od nowa, a R odsuwa stary katalog na scratchu sam):

```bash
cd $SCRATCH/bench/nanoaod-pps-tools && git pull && \
sbatch --export=ALL,STEPS="gate R" test/slurm_final.sbatch
```

Potem `cat $SCRATCH/bench/run2_chain11_gate.txt` (przepływ po erach) i w `bench.csv` to samo
`events_passed` > 0 we wszystkich biegach. Pierwsza powtórka biegnie przy pobieraniu Run 3
w tle (okno czasowe podać przy wynikach); przy rozrzucie r1–r3 powyżej 10% dołożyć R do
zadania z J1 i J3, wcześniej ręcznie odsuwając katalog wyników.

## Kampania

| | co zmienia | wejście | wątki | powtórki | biegów |
|---|---|---|---|---|---:|
| **T1** skalowanie silne | liczbę wątków przy stałym problemie | `DS_CORE` | off, 1–48 | 5 | 150 |
| **T2** skalowanie słabe | problem i wątki naraz | `WEAK_PATTERN` | N | 3 | 54 (real: 63) |
| **T4** struktura zapytania | lazy / eager / `Report()` × długość łańcucha 1, 3, 5 | `DS_IMPL` | off | 2 | 18 |
| **T5** implementacje | RDF / correctionlib / Python / uproot, jeden rdzeń | `DS_IMPL` | off | 3 (`chain/python`: 1) | 34 + 3 |
| **T6** szerokość pliku | T1 na kopii z 6 kolumnami zamiast ~2000 gałęzi | `DS_SLIM` | off, 1–48 | 3 | 90 |
| **T2S** słabe na slim | T2 na kopiach slim | `WEAK_SLIM_PATTERN` | N | 3 | 54 (real: 63) |

`plot_results.py` dodatkowo sprawdza, że w T5 wszystkie implementacje dały tę samą liczbę
(zdarzeń po filtrze, trafień efektywności), czyli powtarza kontrolę `validate.py` na danych,
na których naprawdę mierzono.

„off” to `--threads 0`, czyli bez `EnableImplicitMT`. Punkt `t0` w T1 i T6 to drugi punkt
odniesienia dla przyspieszenia: `ImplicitMT(1)` idzie ścieżką zadaniową i jest wolniejsze od
wersji bez MT (na Aresie filtr: 4.14 s vs 3.17 s).

T4 i T5 są jednowątkowe celowo. uproot uruchamia własne wątki mimo `TrivialExecutor` w obu
executorach (na Aresie 442–444% CPU, `cores_busy_loop` 5.4–6.1), więc T5 jest przypinany do
jednego rdzenia z zewnątrz: `taskset -c $PIN_CORE` dla każdej implementacji. Rekord ma wtedy
`pinned_core`, a `cpus_allowed` i `os_threads` (wątki procesu na końcu biegu) pokazują, czy
proces rzeczywiście był ograniczony. Trzy biegi `r1_impl_*_uproot-default` (`--tag own-threads`)
to uproot bez przypięcia, tak jak dostaje go użytkownik; na wykresie 08 są osobnymi słupkami.

Biegi RDF w T5 mają tę samą konfigurację co `t0` w T1, a przy jednym powtórzeniu wychodziły
o 12–24% wolniej (łańcuch 11.07 s wobec 9.83 s, efektywność 7.69 s wobec 6.22 s, przy
`cores_busy_loop` 0.82–0.89 zamiast 1.00, jak w odrzucanych biegach `warmup_*`). Dlatego T5
ma 3 powtórzenia (poza `chain/python`, ~16 min), a `plot_results.py` wypisuje, o ile mediana
T5 odbiega od mediany T1 t0. Do porównania z innymi implementacjami w pracy lepsza jest ta
druga (5 powtórzeń).

T6 potwierdził hipotezę, że sufit skalowania na `ds_x32` bierze się z szerokości pliku. Każdy
dodatkowy wątek roboczy na pełnym pliku kosztuje (wydruk „per extra thread”):

| | RSS | odczyt w pętli | CPU w pętli |
|---|---:|---:|---:|
| pełny schemat (1984 gałęzie) | +243–245 MB | +17.98 MB | +0.94–1.03 s |
| slim (6 kolumn) | +1–3 MB | +0.05 MB | +0.04–0.11 s |

17.98 MB to dokładnie `bytes_jit`, czyli nagłówek TTree. Każdy wątek czyta i rozwija własną
kopię drzewa ze wszystkimi gałęziami, a przy wielu wątkach te budowy się serializują
(`cores_busy_loop` nasyca się na 12–14). Przyspieszenie względem wersji bez MT przy 48 wątkach:
0.79× / 2.26× / 1.37× (filtr / łańcuch / efektywność) na pełnym pliku wobec 14.8× / 18.5× /
10.9× na slim, a RSS 12.4 GB wobec 0.5–0.7 GB. Również różnica `ImplicitMT(1)` wobec wersji
bez MT to jedna taka kopia: 4.14 s wobec 3.17 s na pełnym pliku, 3.21 s wobec 3.17 s na slim.

Z tego wynikają dwa zastrzeżenia do interpretacji:

- Optimum liczby wątków w T1 nie jest cechą RDataFrame, tylko pary „rozmiar problemu × szerokość
  schematu”: stały ~1 CPU-s na wątek wobec 3–10 CPU-s całej pracy. Przy większym wejściu
  optimum przesunie się w prawo. Dopasowane $s$ z Amdahla (0.26) nie jest kodem szeregowym;
  zmierzony udział setup+JIT to 0.17.
- W T2 jednostka pracy (`ds_x1`, 0.24–0.52 s pętli na wątek) jest mniejsza niż koszt budowy
  drzewa w wątku, więc dopasowane 75–81 ms/wątek to głównie ten narzut. T2S powtarza T2 na
  kopiach slim i oddziela skalowanie samej pracy od szerokości pliku. Brakujące kopie
  (`ds_xN_slim.root`, dla list `weak_N_slim.txt`) tworzy `make_slim.py` przed rozgrzaniem cache.

T3 (pamięć) nie ma własnych biegów: każdy bieg zapisuje `peak_rss_kb` i ślad
`rss_<label>.csv` próbkowany co 0.1 s.

Przed T1 wszystkie pliki są czytane w całości (`cat > /dev/null`), żeby pierwszy bieg na
każdym pliku nie płacił za zimny odczyt z Lustre. Potem idą trzy odrzucane biegi `warmup_*`,
które płacą za zimne biblioteki ROOT-a; wykresy ich nie używają.

Razem **406 biegów, ~1.5 h** na serii syntetycznej (poprzednia kampania bez T2S i powtórzeń
T5: 327 biegów, 1.12 h) i **424 biegi, ~3–4 h** na prawdziwych danych (T1, T2 i T6 na ~4×
większym wejściu). Najdroższy jest `chain/python` z T5 (~990 s, ~16.6 GB RSS na 11 mln zdarzeń).
Każdy bieg ma limit `RUN_TIMEOUT` (2400 s); bieg, który go przekroczy albo się wywali, trafia do
`raw.jsonl` jako `"status": "failed"`.

Czas mierzony jest w fazach `setup`, `warmup`, `jit` i `loop`; porównywalna między
implementacjami jest tylko `loop`. Dla każdej fazy zapisywany jest też czas CPU procesu
(`cpu_<faza>`, suma po wątkach), a `cores_busy_loop = cpu_loop / wall_loop` mówi, ile rdzeni
średnio pracowało w pętli. `cpu_percent` z GNU time uśrednia po całym procesie, razem z ~5 s
jednowątkowego setupu, więc zaniża wykorzystanie wątków.

## Uruchomienie na Aresie

Jednorazowo, w `$SCRATCH/bench`:

```bash
curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba
mkdir -p micromamba && mv bin micromamba/
export MAMBA_ROOT_PREFIX=$SCRATCH/bench/micromamba
eval "$(./micromamba/bin/micromamba shell hook -s bash)"

git clone <repo-url> nanoaod-pps-tools
micromamba env create -f nanoaod-pps-tools/test/environment.yml
micromamba activate pps-bench
cd nanoaod-pps-tools && git lfs install && git lfs pull   # examples/test.root ma mieć ~240 MB
```

Seria syntetyczna w `$SCRATCH/bench/data`, listy prawdziwych danych (Tier0 2023) w
`$SCRATCH/bench/real` (jak powstały: `archive/README.md`, „Transfer z EOS na Ares”). Potem:

```bash
DRY_RUN=1 DATA_DIR=$SCRATCH/bench/data ./test/run_benchmark.sh | tail -1                 # 406
DRY_RUN=1 DATASET=real DATA_DIR=$SCRATCH/bench/real ./test/run_benchmark.sh | tail -1    # 424
DRY_RUN=1 DATASET=big  DATA_DIR=$SCRATCH/bench/data ./test/run_benchmark.sh | tail -1    # 99
DRY_RUN=1 DATASET=big TESTS=sizepy DATA_DIR=$SCRATCH/bench/data ./test/run_benchmark.sh | tail -1   # 21
sbatch test/slurm_benchmark.sbatch                              # -> results-ares
sbatch --export=ALL,DATASET=real test/slurm_benchmark.sbatch    # -> results-ares-real
```

Kopie slim (`ds_x32_slim.root` i `ds_xN_slim.root` albo `core_slim.txt`, `weak_N_slim.txt` +
`slim/`) powstają przy pierwszym zadaniu, jeśli ich nie ma.

`slurm_benchmark.sbatch` bierze cały węzeł (`--exclusive`, `--mem=0`, `--hint=nomultithread`),
wypisuje `lscpu`/`nproc` i przerywa, jeśli widzi mniej CPU niż zamówił. Nie używa `srun`: od
Slurm 22.05 krok zadania nie dziedziczy `--cpus-per-task`, co po cichu spłaszcza krzywą
przyspieszenia. Istniejący katalog wyników jest przenoszony do `results-ares-archived-<data>`,
chyba że zadanie ma `RESUME=1`: wtedy dopisuje do niego i pomija etykiety, które w `raw.jsonl`
mają już `"status": "ok"`. Tak wznawia się zadanie, któremu skończył się `--time`. Biegi `failed`
są powtarzane, a `warmup_*` idą zawsze.

### Wejścia w RAM-ie (MEMFS)

```bash
sbatch -C memfs --export=ALL,STORAGE=memfs test/slurm_benchmark.sbatch                  # -> results-ares-memfs
sbatch -C memfs --export=ALL,DATASET=real,STORAGE=memfs test/slurm_benchmark.sbatch     # -> results-ares-real-memfs
```

`-C memfs` tworzy dla zadania dysk w RAM-ie pod `$MEMFS` (maks. 120 GB, wlicza się do `--mem`).
Z `STORAGE=memfs` skrypt kopiuje cały `DATA_DIR` do `$MEMFS/data` przed kampanią i dopiero
potem uruchamia te same biegi, więc żaden bieg nie czyta z Lustre. Różnica względem zwykłej
kampanii to koszt współdzielonego systemu plików. Skrypt przerywa, jeśli `$MEMFS` nie istnieje,
dane się nie mieszczą albo lista `.txt` ma ścieżkę bezwzględną (wskazywałaby dalej na Lustre).
Wyniki idą na scratch, nie do MEMFS. Każdy rekord ma pole `storage` (`lustre`/`memfs`).
Kopie slim muszą już istnieć, czyli najpierw puść zwykłą kampanię; inaczej `make_slim.py`
zapisze je w MEMFS i znikną razem z zadaniem.

### Kampania na ~1 TB (`DATASET=big`)

Najpierw jednorazowo kopie, na węźle logowania w `tmux`/`screen` (kilkanaście minut do godziny):

```bash
hpc-fs                                                            # potrzeba ~1.04 TB
bash test/make_bigset.sh --source $SCRATCH/bench/data/ds_x32.root # -> data/ds_1.root ... ds_96.root
```

Potem dwa zadania, oba do `results-ares-big`:

```bash
# A: ~3.5 h, 99 biegów -- T1 i T2 do 1 TB, T4 na ~100 GB, seria rozmiarów dla RDF i uproot
sbatch --time=06:00:00 --export=ALL,DATASET=big test/slurm_benchmark.sbatch
# B: ~9 h, 21 biegów -- ta sama seria dla Pythona, dopisana do wyników A
sbatch --time=12:00:00 --dependency=afterany:<id zadania A> \
    --export=ALL,DATASET=big,TESTS=sizepy,RESUME=1 test/slurm_benchmark.sbatch
```

`afterany` uruchamia B, gdy A się skończy, niezależnie od tego, jak się skończyło. Nie puszczaj
obu naraz: dopisywałyby do tego samego `raw.jsonl` i dzieliły Lustre, a to psuje zimne odczyty.

Wejście to 96 zwykłych kopii `ds_x32.root` (96 × 10.84 GB, ~1.04 TB, 1.065 mld zdarzeń), czyli
`ds_1.root` … `ds_96.root` w tym samym `data/`. `make_bigset.sh` tylko kopiuje: 8 strumieni `cp`,
przez nazwy `.partial`, z pominięciem kopii, które już są w dobrym rozmiarze, więc przerwane
kopiowanie wystarczy powtórzyć. Na końcu sprawdza, że wszystkie 96 ma pełny rozmiar. `df`
sprawdza wolne miejsce, ale limit grantu pokazuje tylko `hpc-fs`. Listy nad kopiami
(`lists/core.txt` = 96, `lists/weak_N.txt` = 2N, `lists/impl.txt` = 9, `lists/size_N.txt` = N
pierwszych kopii) pisze sam `run_benchmark.sh` na starcie każdego zadania. Jeśli kopii brakuje,
zadanie kończy się od razu z poleceniem, które je zrobi.

Nie `hadd`: scalanie 1 TB w jeden plik to godziny, a wynikowy plik ma inne granice klastrów niż
źródło, czyli zmienia to, po czym `ImplicitMT` dzieli pracę. `cp` zachowuje i klastry, i kodek.

**Dlaczego kopie, a nie jeden plik wpisany 96 razy na listę.** Kopia to osobny inode. Jeden plik
byłby przeczytany raz z Lustre i 95 razy z page cache, czyli kampania mierzyłaby cache. Przy
kopiach `COLD=1` (domyślne dla `big`) przed każdym biegiem wyrzuca strony wejścia z cache przez
`posix_fadvise(POSIX_FADV_DONTNEED)` — bez roota i tylko na plikach wejściowych, więc biblioteki
ROOT-a zostają ciepłe. Każdy bieg czyta wszystko z Lustre, dokładnie jak przy 96 różnych
plikach. Zawartość jest identyczna, więc wyniki dalej da się sprawdzić: zdarzeń ma być 96×,
a checksumy wszystkich biegów muszą się zgadzać. Rekord ma pole `cache` (`warm`/`cold`).

Zamiast rozgrzewania przez `cat` (przeczytałoby 1 TB na darmo) jest samosprawdzenie: skrypt
wyrzuca strony pierwszej kopii i pyta `fincore`, ile zostało. Jeśli zostały, przerywa, bo inaczej
każdy „zimny” pomiar byłby ciepły. `fincore` to util-linux ≥ 2.31; jak go nie ma, leci tylko
ostrzeżenie. Trzy odrzucane biegi `warmup_*` idą wtedy na jednej kopii — są po biblioteki i PCH,
nie po dane, więc trwają sekundy. MEMFS tu nie pomoże: ma 120 GB, więc 1 TB się nie zmieści (skrypt to odrzuci), a do
tego zabierałby RAM ścieżkom Python i uproot i dawałby odczyt najcieplejszy z możliwych.

Domyślnie 1 powtórzenie (`REPEATS_*=1`), bo samo skalowanie silne to tu ~2 h, więc na wykresach
nie będzie wąsów.

**Co się mierzy.** Tylko to, czego `ds_x32` nie mógł pokazać. `TESTS` wybiera eksperymenty;
dla `big` domyślnie `TESTS="strong weak qstruct size"` (zadanie A), a zadanie B to
`TESTS=sizepy`. Każde zaczyna się od 3 rozgrzewek.

| `TESTS` | test | wejście | biegów | ~czas | zadanie |
|---|---|---|---:|---:|---|
| `strong` | T1 skalowanie silne, wątki off, 1–48 | 96 kopii, ~1 TB | 30 | 2.2 h | A |
| `weak` | T2 skalowanie słabe, N wątków | 2N kopii, do ~1 TB | 21 | 0.5 h | A |
| `qstruct` | T4 lazy / eager / `Report()` × 1, 3, 5, jeden wątek | `lists/impl.txt`, ~98 GB | 9 | 15 min | A |
| `size` | T5 względem rozmiaru: RDF i uproot, jeden rdzeń | 1–9 kopii, ~11–98 GB | 36 | 30 min | A |
| `sizepy` | T5 względem rozmiaru: Python, jeden rdzeń | 1–9 kopii, ~11–98 GB | 18 | 9 h | B |
| `impl`, `slim`, `weakslim` | T5 na jednym wejściu, T6, T2S | — | — | — | pominięte |

T4 biegnie na ~100 GB, a nie na 1 TB, bo `rdf-eager` czyta wejście do 6 razy. T5 jest tu serią
rozmiarów, bo Python i uproot trzymają całe kolumny w pamięci i na 1 TB by padły. T6 i T2S nie
zależą od rozmiaru wejścia. Serie `size` i `sizepy` mają te same warianty co wykres 08: filtr
`rdf`, `uproot`, `python --mode loop`; łańcuch `rdf-lazy`, `uproot`, `python`; efektywność
`jit`, `uproot`, `python --mode loop`. Etykiety to `r1_size_<test>_<impl>_c<N>`, gdzie N to
liczba kopii.

**Python osobno i na końcu.** Łańcuch w Pythonie to ~16 min i ~16.6 GB RSS na kopię, więc na
8–9 kopiach potrzebuje ~133–150 GB z ~184 GB węzła. `sizepy` biegnie od najmniejszego rozmiaru,
najpierw filtr i efektywność, a łańcuch na samym końcu. Jeśli zabraknie pamięci, jądro zabija
tylko ten jeden proces. `run_one` zapisuje go jako `"status": "failed"` (kod 137) i kampania idzie
dalej, a wszystko wcześniej jest już w `raw.jsonl`. Wariant, który padł na N kopiach, nie jest
uruchamiany na większych: dostają rekord `failed` z `skipped_after` = N, bo i tak by padły po
nawet ~2 h czytania. Slurm może pokazać stan `OUT_OF_MEMORY`, ale wyniki zostają.
`RUN_TIMEOUT=14400` mieści łańcuch w Pythonie na 9 kopiach (~2.5 h).

Do pracy jedna uwaga: „1 TB” to rozmiar plików, a pętla czyta z nich tylko używane gałęzie —
od ~5 GB przy jednym wątku do ~90 GB przy 48 (`bytes_loop` rośnie z liczbą wątków, bo każdy
czyta własny nagłówek drzewa).

`$SCRATCH` jest czyszczony po ~30 dniach, więc wyniki skopiuj do `$PLG_GROUPS_STORAGE/<grant>/`.
`MaxRSS` z `sacct` (na końcu logu) powinien zgadzać się z `time_maxrss_kb` w `bench.csv`.

## Uruchomienie lokalnie

```bash
brew install coreutils gnu-time      # macOS: gtime i gtimeout, inaczej brak limitu i CPU%
python test/validate.py --threads 4
THREADS_LIST="1 2 4 8" WEAK_SERIES="1 2 4 8" REPEATS_STRONG=1 DATA_DIR=... ./test/run_benchmark.sh
python test/plot_results.py --results test/results
```

Skrypty same wybierają `.venv/bin/python`, jeśli istnieje; inny interpreter ustawisz przez `PY=`.
Domyślnie T1, T4 i T5 używają `ds_x32`, a ścieżka pythonowa materializuje całe kolumny
(~16 GB RSS), więc na laptopie z małą ilością RAM-u T5 wejdzie w swap. `DS_CORE=... DS_IMPL=...`
pozwala podać mniejsze wejście.

## Wyniki

Pełna mapa katalogów `results/` (co skąd, co idzie do pracy, co czeka na pomiar) jest
w [`results/README.md`](../results/README.md). W skrócie: na Heliosie wszędzie łańcuch 11 filtrów
na jednym zbiorze ~1 TB naraz, czytanym z dysku po wyczyszczeniu page cache:

| katalog | dane | w pracy |
|---|---|---|
| `single-core-ares/` | Ares, 1 rdzeń: 1–9 kopii `ds_x32`, łańcuch 5 filtrów | RDF / uproot / Python, struktura zapytania |
| `full-chain11/artificial-1tb/` | 96 kopii `ds_x32`, 1,04 TB (zadanie F) | rysunek pełnych plików, tabela zbiorów |
| `full-chain11/run2-1tb/` | Run 2 Open Data, 653 pliki, 1,04 TB, `--period 2016` (zadanie R) | jak wyżej |
| `run3/` | Run 3 `core.txt` (J1) i `weak_N` (J2) | jak wyżej; J2 obok T2 slim |
| `synthetic-slim/` | 96 plików slim (10 gałęzi), 29,8 mld zdarzeń, 1,54 TB | skalowanie, gdy pętla czyta cały zbiór |
| `comparison/` | `plot_real_vs_synthetic.py` z katalogów powyżej | `full_files_chain11.png`, `sets_summary.{csv,tex}` |
| `archive/` | łańcuch 5 filtrów na pełnych plikach Heliosa (`chain5/`), sesja slim r5/r6, dawne 10 GB | — |

| plik | co pokazuje | test |
|---|---|---|
| `01_speedup_amdahl.png` | przyspieszenie vs wątki, dopasowanie Amdahla | T1 |
| `02_parallel_efficiency.png` | efektywność równoległa [%] | T1 |
| `03_weak_scaling.png` | czas przy stałej pracy na wątek z dopasowaniem `w + c·N`, przyspieszenie skalowane; slim przerywaną | T2, T2S |
| `04_rss_vs_threads.png` | koszt pamięciowy wątku | T3 |
| `05_rss_vs_size.png` | RSS wzdłuż serii słabej | T3 |
| `06_rss_over_time.png` | profil RSS w czasie, po krzywej na liczbę wątków; w kampaniach sprzed `slurm_memtrace.sbatch` (`archive/`) bez próbek z pętli (przerywana linia) | T3 |
| `07_query_structure.png` | liczba pętli po zdarzeniach i jej koszt | T4 |
| `08_implementations.png` | zdarzenia/s z liczbą zajętych rdzeni w pętli przy każdym słupku (i „pinned”) oraz rozbicie na fazy, osobno filter/chain/efficiency | T5 |
| `09_speedup_baselines.png` | przyspieszenie względem `ImplicitMT(1)` i względem wersji bez MT | T1 |
| `10_cores_busy.png` | ile rdzeni pracowało w pętli, pełny plik i slim | T1, T6 |
| `11_file_width.png` | czas pętli, przyspieszenie i RSS: pełny schemat vs slim | T6 |
| `13_input_size.png` | szczyt RSS i czas całkowity (setup + JIT + pętla) względem rozmiaru wejścia w GB, RDF / uproot / Python | `size`, `sizepy` |
| `full_files_chain11.png` (w `results/comparison/`) | łańcuch 11 filtrów na pełnych plikach ~1 TB: czas pętli, przyspieszenie i szczytowy RSS względem wątków, po serii na zbiór (`plot_real_vs_synthetic.py --figure`) | T1 |
| `sets_summary.{csv,tex}` (w `results/comparison/`) | tabela zbiorów: zdarzenia, TB, kodek, gałęzie i koszyki na plik, odczyt w pętli (GB i %), najszybszy punkt, plateau 5%, $E$ przy 96, MB na wątek, GB/s w maksimum | T1 |

Wykresy 14–16 (optimum względem rozmiaru, sztuczne vs Open Data i układ pamięci na łańcuchu
5 filtrów) leżą w `results/archive/chain5/`, a ich skrypty w `archive/`.

Przy `DATASET=big` nie ma biegów T5, więc wykres 08 powstaje z największego punktu serii
rozmiarów (9 kopii, ~98 GB). Na konsolę trafiają też nachylenia z serii (GB RSS i sekundy na
1 GB wejścia) oraz rozmiar, od którego RDF jest w sumie szybszy od uproot.

Wąsy na wykresach 01–04 i 09–11 to min–max z powtórzeń, punkt to mediana.

Obok wykresów powstaje `table_scalability_<test>.tex` (`filter`, `chain`, `efficiency`), czyli
tabela skalowalności z pracy (`tab:scalability`) liczona z T1: czas pętli przy `ImplicitMT(n)`,
czas całego procesu, przepustowość, przyspieszenie i efektywność względem `ImplicitMT(1)` oraz
„cores busy”, czyli CPU samej pętli przez jej czas. Przepustowość, przyspieszenie i efektywność
liczone są z czasu pętli. Czas całego procesu (z GNU time) obejmuje start Pythona i ROOT-a,
otwarcie plików i JIT: na 1 TB pełnych plików to ~24 s stałego kosztu przy pętli 13 s, na zbiorze
slim ~5 s przy 334 s. Podpis sam podaje liczbę zdarzeń, liczbę powtórzeń, zimny odczyt i maksimum.

`summary_strong_<test>.csv` to podsumowanie tego samego dla każdej zmierzonej liczby wątków
(nie tylko `TABLE_THREADS`): liczba biegów, mediana, minimum i maksimum czasu pętli, czas całego
procesu, stały koszt (setup, rozgrzewka, JIT), przepustowość, przyspieszenie, efektywność
i „cores busy”. Biegi pominięte przez regułę `OUTLIER_FACTOR` nie wchodzą do żadnej z tych
liczb. Rekordy sprzed poprawki parsera GNU time gubiły godziny w `elapsed_s` (bieg 8,6 h
zapisany jako 34 min); `plot_results.py` je odtwarza, bo proces trwa zawsze dłużej niż jego fazy,
a różnica to sekundy.
Powstaje też przy `--csv-only`.

Na konsolę trafiają też: frakcja szeregowa $s$ z Amdahla i **zmierzony** udział setup + JIT
przy jednym wątku. Jeśli dopasowane $s$ jest wyraźnie większe od zmierzonego, degradacja ma
przyczynę poza kodem szeregowym (optimum liczby wątków liczy `archive/plot_optimum.py`). Dalej: koszt na wątek z T2 i T2S (ms/wątek), najlepsze
przyspieszenie względem wersji bez MT, RSS na wątek dla obu plików z T6 oraz sprawdzenie, że
wszystkie biegi T1 i T6 danego testu dały ten sam wynik (checksumy). „per extra thread”
podaje nachylenia RSS, odczytu i CPU pętli względem liczby wątków dla T1 i T6, a „T5 … against
T1 t0” różnicę między identycznymi biegami RDF z T5 i z T1.

## Zmienne środowiskowe

| zmienna | domyślnie | znaczenie |
|---|---|---|
| `DATASET` | `synthetic` | `synthetic` (`ds_xN`), `real` (listy z `archive/make_filelists.py`) albo `big` (kopie z `make_bigset.sh`) |
| `DATA_DIR` | `test/data` | katalog z wejściami |
| `DS_CORE` / `DS_IMPL` / `DS_SLIM` | zależnie od `DATASET` (tabela w „Dane”) | wejścia T1 / T4–T5 / T6 |
| `WEAK_PATTERN` | `ds_x%s.root` / `weak_%s.txt` | wejście T2, `%s` = N |
| `WEAK_SLIM_PATTERN` | `ds_x%s_slim.root` / `weak_%s_slim.txt` | wejście T2S, tworzone automatycznie |
| `PIN_CORE` | `2` | rdzeń, do którego `taskset` przypina T5 (bez `taskset`: bez przypięcia, z ostrzeżeniem) |
| `RESULTS` | `test/results` (w `slurm_benchmark.sbatch`: `$SCRATCH/bench/results-$MACHINE[-big\|-real]`) | katalog wyjściowy |
| `MACHINE` | `local` (w `slurm_benchmark.sbatch`: `ares`) | trafia do każdego rekordu |
| `THREADS_LIST` | `1 2 4 8 12 16 24 32 48` | sweep wątków w T1 i T6 |
| `THREAD_SCALE` | `linear` przy siatce do ≥96 wątków, inaczej `log` | skala osi wątków (i osi przyspieszenia) w `plot_results.py` |
| `TABLE_THREADS` | `1 2 4 8 12 16 24 32 48 64 80 88 96 104 112 128 144 160 176 192` | wiersze tabel `table_scalability_*.tex` w `plot_results.py`; najszybszy punkt jest dokładany zawsze |
| `OUTLIER_FACTOR` | `1.5` | `plot_results.py` (i `archive/plot_optimum.py`) pomija bieg, którego pętla trwa dłużej niż tyle razy mediana tej samej konfiguracji (co najmniej 3 biegi); `0` wyłącza |
| `WEAK_SERIES` | `1 2 4 8 16 32` / `1 2 4 8 16 32 48` | N w T2 |
| `WEAK_UNIT` | `2` | kopii na wątek w punkcie T2 (tylko `big`): `weak_N.txt` ma `WEAK_UNIT`·N kopii |
| `CHAIN_LENS` | `1 3 5` | długości łańcucha w T4 |
| `TESTS` | wszystkie / `strong weak qstruct size` dla `big` | które eksperymenty biegną; `strongchain` to sam T1 łańcucha 5 filtrów (bez t0) |
| `CHAIN_ARGS` | — | dodatkowe argumenty `bench_chain.py` (i `bench_pool.py`) w `strongchain`, `strong11`, `weak11`, `node11` i rozgrzewce łańcucha 11, np. `--period 2016` |
| `SIZE_SERIES` | `1 2 4 6 8 9` | liczby kopii w `size` i `sizepy` (tylko `big`) |
| `NODE_IMPLS` / `NODE_THREADS` | `rdf-lazy uproot-pool python-pool` / `192` | test `node11`: implementacje i liczba wątków (RDF) albo procesów (pule) |
| `EVENT_COUNTS` | — (w `slurm_run3.sbatch`: `data3-full/local.csv`) | CSV z `archive/inventory_files.py`: liczba zdarzeń z niego zamiast otwierania każdego pliku w `setup` (~5 min na bieg przy 1453 plikach); gdy pliku w nim brak, pliki są otwierane jak dotąd |
| `BIG_COPIES` / `IMPL_COPIES` | `96` / `9` | ile kopii `ds_N.root` ma `lists/core.txt` / `lists/impl.txt` (tylko `big`) |
| `RESUME` | — | `1` dopisuje do `raw.jsonl` i pomija biegi, które są już `ok` |
| `REPEATS_STRONG` / `_WEAK` / `_QSTRUCT` / `_IMPL` / `_SLIM` | `5` / `3` / `2` / `3` / `3` | powtórzenia (mediana, wąsy min–max) |
| `RUN_TIMEOUT` | `2400` (w `slurm_benchmark.sbatch` dla `big`: `14400`) | limit na bieg [s] |
| `VALIDATE_THREADS` | `8` | liczba wątków w teście 1 vs N w `run_all.sh` |
| `SAMPLE_INTERVAL` | `0.1` | okres próbkowania RSS [s]; na Linuksie próbkuje osobny proces, więc także w trakcie pętli |
| `DRY_RUN` | — | `1` wypisuje biegi bez uruchamiania |
| `PY` | `.venv/bin/python` lub `python3` | interpreter |

## Po zmianie geometrii lub kernela

`validate.py` porównuje wygenerowany C++ z `diamond_geometry.assign_region` na 100k punktów;
uruchom go po każdej zmianie w `POT_CONFIG` lub `get_cpp_source`. Cling nie pozwala
redefiniować funkcji w tym samym procesie, więc zmiany kernela sprawdzaj w świeżym procesie.
