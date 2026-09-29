# Benchmark: RDataFrame vs Python na NanoAOD

Jedna ścieżka: `slurm_benchmark.sbatch` → `run_all.sh` → `validate.py` + `run_benchmark.sh`
→ `plot_results.py`. Te same eksperymenty idą na dwóch zbiorach: syntetycznej serii
`ds_x1`–`ds_x32` (`DATASET=synthetic`, domyślnie) i prawdziwych plikach NanoAOD z Tier0
(`DATASET=real`).

| plik | rola |
|---|---|
| `run_all.sh` | sprawdza środowisko i Git LFS, uruchamia walidację, potem kampanię |
| `validate.py` | zgodność wszystkich implementacji, geometria C++ vs Python, 1 vs N wątków |
| `run_benchmark.sh` | kampania T1/T2/T4/T5/T6/T2S, zbiera `raw.jsonl`, na końcu rysuje wykresy |
| `make_slim.py` | kopia wejścia T1 z samymi 6 używanymi kolumnami (plik albo lista) dla T6 |
| `inventory_files.py` | CSV z opisem plików: zdarzenia, klastry, schemat, kodek, obecność PPS; sprawdza transfer |
| `make_filelists.py` | z inwentaryzacji buduje listy `core.txt`, `weak_N.txt`, `impl.txt` dla `DATASET=real` |
| `bench_filter.py`, `bench_chain.py`, `bench_efficiency.py` | pojedynczy pomiar (TEST 1–3) |
| `bench_common.py` | parser argumentów, fazy czasu, liczniki bajtów i RSS, rekord `BENCH` |
| `impl_rdf.py`, `impl_python.py`, `impl_uproot.py` | implementacje mierzonych operacji |
| `plot_results.py` | `raw.jsonl` → `bench.csv` + wykresy (nie wymaga ROOT-a, tylko matplotlib) |
| `slurm_benchmark.sbatch` | zadanie na Aresie (cały węzeł, `--exclusive`) |
| `environment.yml` | środowisko `pps-bench` (ROOT, correctionlib, uproot, awkward, matplotlib) |

## Dane

Każde wejście benchmarku (`--input`) to plik `.root` albo lista `.txt` (jedna ścieżka na linię;
ścieżki względne liczone od katalogu listy). `run_benchmark.sh` przed startem sprawdza, że
istnieje każde wejście i każdy plik z każdej listy.

| rola | `DATASET=synthetic` | `DATASET=real` |
|---|---|---|
| T1 (`DS_CORE`) | `ds_x32.root` | `core.txt` |
| T2 (`WEAK_PATTERN`) | `ds_x%s.root`, N = 1…32 | `weak_%s.txt`, N = 1…48 |
| T4, T5 (`DS_IMPL`) | `ds_x32.root` | `impl.txt` (~11 mln zdarzeń) |
| T6 (`DS_SLIM`) | `ds_x32_slim.root` | `core_slim.txt` + `slim/` |

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

### Prawdziwe: Tier0 replay 2023

Pliki z `/eos/cms/store/backfill/1/data/Tier0_REPLAY_2023/<PD>/NANOAOD/<wersja>/000/<run>/`.
Kryteria wyboru (egzekwuje je `make_filelists.py`):

- jeden run i jedna wersja przetwarzania, domyślnie **run 369998, `PromptReco-v21141959`**
  (~75 plików z różnych primary datasetów); inne runy i wersje mają inne menu HLT i inne CMSSW,
  czyli inny schemat;
- jeden skrót schematu (SHA-256 posortowanych nazw gałęzi), ten z największą liczbą zdarzeń;
- wszystkie 6 kolumn benchmarku obecne i `nPPSLocalTrack > 0` w co najmniej 1% zdarzeń;
- pliki **nie są łączone**: RDataFrame czyta listę, tak jak w analizie, a klastry zostają takie,
  jakie zapisał Tier0.

Zestawy (`make_filelists.py`, wartości z `sets.json` po inwentaryzacji na Aresie):

| lista | cel | domyślny rozmiar |
|---|---|---|
| `core.txt` | T1, T6 | do 45 mln zdarzeń albo 60 GB (budżet page cache: 192 GB RAM, ~12 GB RSS przy 48 wątkach) |
| `weak_N.txt` | T2 | ~N × (zdarzenia `core` / 48); odchylenie od celu i klastry na wątek w `sets.json` |
| `impl.txt` | T4, T5 | ~11 mln zdarzeń, jak `ds_x32`, żeby Python w T5 zmieścił się w ~20 min |

Dwie różnice wobec serii syntetycznej, które trzeba opisać razem z wynikami: kodek (produkcyjny
NanoAOD to zwykle LZMA, `ds_xN` to ZSTD:5; dekompresja to większość kosztu na zdarzenie) i
rozmiar klastrów. Oba są w kolumnach `compression` i `events_per_cluster` inwentaryzacji.

## Transfer z EOS na Ares

**1. Inwentaryzacja na lxplus** (tylko odczyt; `files.txt` to lista ścieżek jak z
`find . -name '*.root'`, względem `/eos/cms/store`):

```bash
source /cvmfs/sft.cern.ch/lcg/views/LCG_105/x86_64-el9-gcc12-opt/setup.sh
git clone <repo-url> nanoaod-pps-tools && cd nanoaod-pps-tools
ls /eos/cms/store/backfill/1/data/Tier0_REPLAY_2023/ | head     # sprawdź prefiks
python test/inventory_files.py --list files.txt --prefix /eos/cms/store --output inventory_lxplus.csv
python test/make_filelists.py --inventory inventory_lxplus.csv --run 369998 \
    --version PromptReco-v21141959 --transfer-list transfer.txt --strip-prefix /eos/cms/store
```

Podsumowanie na końcu inwentaryzacji grupuje pliki po (run, wersja, schemat) i pokazuje
zdarzenia, GB i średni odsetek zdarzeń z PPS. `make_filelists.py` wypisuje, ile GB trzeba przesłać.

**2. Transfer: push z lxplus przez `rsync`**, w `tmux`, 4 strumienie naraz:

```bash
DEST=plgLOGIN@ares.cyfronet.pl:/net/ascratch/people/plgLOGIN/bench/real/   # sprawdź: echo $SCRATCH
xargs -P 4 -I{} rsync -aR --partial /eos/cms/store/./{} "$DEST" < transfer.txt
```

`-R` z `/./` odtwarza strukturę katalogów od `backfill/...`, `--partial` pozwala wznowić przerwany
plik (wystarczy uruchomić tę samą komendę ponownie), a `-P 4` puszcza 4 pliki naraz. Oczekiwana
przepustowość CERN → Cyfronet to rząd 50–200 MB/s łącznie, czyli ~100 GB w 10–30 min. Logowanie
na Ares kluczem ssh z hasłem przez `ssh-agent`; klucza nie kopiuj do repo ani na scratch.

Wariant zapasowy, jeśli rsync jest wolny: pull na Aresie przez xrootd (`micromamba install -c
conda-forge xrootd` w `pps-bench`) z proxy CMS VOMS zrobionym na lxplus:

```bash
# lxplus: voms-proxy-init -voms cms -valid 24:00, potem scp pliku proxy na Ares (chmod 600)
export X509_USER_PROXY=$HOME/.x509up_cms       # poza repo i poza katalogiem wyników
sed 's|^|root://eoscms.cern.ch//eos/cms/store/|' transfer.txt > urls.txt
xrdcp --parallel 4 --infiles urls.txt $SCRATCH/bench/real/
rm -f "$X509_USER_PROXY"                        # po transferze
```

Proxy to poświadczenie X.509: krótka ważność, uprawnienia 600, nigdy w repo ani w skryptach.
Ten wariant spłaszcza strukturę katalogów, co niczemu nie szkodzi, bo nazwy plików to UUID.

**3. Weryfikacja i listy na Aresie:**

```bash
cd $SCRATCH/bench/real
find $PWD -name '*.root' -not -path '*/slim/*' > ares_files.txt
python $SCRATCH/bench/nanoaod-pps-tools/test/inventory_files.py --list ares_files.txt \
    --output inventory_ares.csv --compare inventory_lxplus.csv
python $SCRATCH/bench/nanoaod-pps-tools/test/make_filelists.py --inventory inventory_ares.csv \
    --run 369998 --version PromptReco-v21141959
```

`inventory_lxplus.csv` skopiuj wcześniej na Ares (`scp`). `--compare` porównuje liczbę zdarzeń
i rozmiar każdego pliku z inwentaryzacją z lxplus i kończy się kodem 1, jeśli choć jeden się
różni. Inwentaryzacja na Aresie liczy też `pps_fraction` (czyta tylko dwie małe gałęzie), więc
`make_filelists.py` stosuje te same kryteria co na lxplus. Listy i `sets.json` trafiają do
`$SCRATCH/bench/real`, czyli tam, gdzie `slurm_benchmark.sbatch` ustawia `DATA_DIR` dla
`DATASET=real`.

**Pojemność.** `hpc-fs` na Aresie pokazuje limity; scratch ma limity liczone w TB, więc
~100–200 GB się zmieści. Scratch jest czyszczony po ~30 dniach nieużywania. Rzeczywistym
ograniczeniem jest RAM węzła na page cache, stąd limit 60 GB dla `core.txt`.

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

Seria syntetyczna w `$SCRATCH/bench/data`, listy prawdziwych danych w `$SCRATCH/bench/real`
(sekcja „Transfer z EOS na Ares”). Potem:

```bash
DRY_RUN=1 DATA_DIR=$SCRATCH/bench/data ./test/run_benchmark.sh | tail -1                 # 406
DRY_RUN=1 DATASET=real DATA_DIR=$SCRATCH/bench/real ./test/run_benchmark.sh | tail -1    # 424
sbatch test/slurm_benchmark.sbatch                              # -> results-ares
sbatch --export=ALL,DATASET=real test/slurm_benchmark.sbatch    # -> results-ares-real
```

Kopie slim (`ds_x32_slim.root` i `ds_xN_slim.root` albo `core_slim.txt`, `weak_N_slim.txt` +
`slim/`) powstają przy pierwszym zadaniu, jeśli ich nie ma.

`slurm_benchmark.sbatch` bierze cały węzeł (`--exclusive`, `--mem=0`, `--hint=nomultithread`),
wypisuje `lscpu`/`nproc` i przerywa, jeśli widzi mniej CPU niż zamówił. Nie używa `srun`: od
Slurm 22.05 krok zadania nie dziedziczy `--cpus-per-task`, co po cichu spłaszcza krzywą
przyspieszenia. Istniejący katalog wyników jest przenoszony do `results-ares-archived-<data>`.

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

| plik | co pokazuje | test |
|---|---|---|
| `01_speedup_amdahl.png` | przyspieszenie vs wątki, dopasowanie Amdahla i USL | T1 |
| `02_parallel_efficiency.png` | efektywność równoległa [%] | T1 |
| `03_weak_scaling.png` | czas przy stałej pracy na wątek z dopasowaniem `w + c·N`, przyspieszenie skalowane; slim przerywaną | T2, T2S |
| `04_rss_vs_threads.png` | koszt pamięciowy wątku | T3 |
| `05_rss_vs_size.png` | RSS wzdłuż serii słabej | T3 |
| `06_rss_over_time.png` | profil RSS w czasie, po krzywej na liczbę wątków | T3 |
| `07_query_structure.png` | liczba pętli po zdarzeniach i jej koszt | T4 |
| `08_implementations.png` | zdarzenia/s z liczbą zajętych rdzeni w pętli przy każdym słupku (i „pinned”) oraz rozbicie na fazy, osobno filter/chain/efficiency | T5 |
| `09_speedup_baselines.png` | przyspieszenie względem `ImplicitMT(1)` i względem wersji bez MT | T1 |
| `10_cores_busy.png` | ile rdzeni pracowało w pętli, pełny plik i slim | T1, T6 |
| `11_file_width.png` | czas pętli, przyspieszenie i RSS: pełny schemat vs slim | T6 |

Wąsy na wykresach 01–04 i 09–11 to min–max z powtórzeń, punkt to mediana.

Na konsolę trafiają też: frakcja szeregowa $s$ z Amdahla, $\sigma$ i $\kappa$ z USL,
przewidywane optimum liczby wątków i **zmierzony** udział setup + JIT przy jednym wątku. Jeśli
dopasowane $s$ jest wyraźnie większe od zmierzonego, degradacja ma przyczynę poza kodem
szeregowym i opisuje ją $\kappa$. Dalej: koszt na wątek z T2 i T2S (ms/wątek), najlepsze
przyspieszenie względem wersji bez MT, RSS na wątek dla obu plików z T6 oraz sprawdzenie, że
wszystkie biegi T1 i T6 danego testu dały ten sam wynik (checksumy). „per extra thread”
podaje nachylenia RSS, odczytu i CPU pętli względem liczby wątków dla T1 i T6, a „T5 … against
T1 t0” różnicę między identycznymi biegami RDF z T5 i z T1.

## Zmienne środowiskowe

| zmienna | domyślnie | znaczenie |
|---|---|---|
| `DATASET` | `synthetic` | `synthetic` (`ds_xN`) albo `real` (listy z `make_filelists.py`) |
| `DATA_DIR` | `test/data` | katalog z wejściami |
| `DS_CORE` / `DS_IMPL` / `DS_SLIM` | zależnie od `DATASET` (tabela w „Dane”) | wejścia T1 / T4–T5 / T6 |
| `WEAK_PATTERN` | `ds_x%s.root` / `weak_%s.txt` | wejście T2, `%s` = N |
| `WEAK_SLIM_PATTERN` | `ds_x%s_slim.root` / `weak_%s_slim.txt` | wejście T2S, tworzone automatycznie |
| `PIN_CORE` | `2` | rdzeń, do którego `taskset` przypina T5 (bez `taskset`: bez przypięcia, z ostrzeżeniem) |
| `RESULTS` | `test/results` | katalog wyjściowy |
| `MACHINE` | `local` | trafia do każdego rekordu |
| `THREADS_LIST` | `1 2 4 8 12 16 24 32 48` | sweep wątków w T1 i T6 |
| `WEAK_SERIES` | `1 2 4 8 16 32` / `1 2 4 8 16 32 48` | N w T2 |
| `CHAIN_LENS` | `1 3 5` | długości łańcucha w T4 |
| `REPEATS_STRONG` / `_WEAK` / `_QSTRUCT` / `_IMPL` / `_SLIM` | `5` / `3` / `2` / `3` / `3` | powtórzenia (mediana, wąsy min–max) |
| `RUN_TIMEOUT` | `2400` | limit na bieg [s] |
| `VALIDATE_THREADS` | `8` | liczba wątków w teście 1 vs N w `run_all.sh` |
| `SAMPLE_INTERVAL` | `0.1` | okres próbkowania RSS [s] |
| `DRY_RUN` | — | `1` wypisuje biegi bez uruchamiania |
| `PY` | `.venv/bin/python` lub `python3` | interpreter |

## Po zmianie geometrii lub kernela

`validate.py` porównuje wygenerowany C++ z `diamond_geometry.assign_region` na 100k punktów;
uruchom go po każdej zmianie w `POT_CONFIG` lub `get_cpp_source`. Cling nie pozwala
redefiniować funkcji w tym samym procesie, więc zmiany kernela sprawdzaj w świeżym procesie.
