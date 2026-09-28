# Benchmark: RDataFrame vs Python na serii ds_x1–ds_x32

Jedna ścieżka: `slurm_benchmark.sbatch` → `run_all.sh` → `validate.py` + `run_benchmark.sh`
→ `plot_results.py`.

| plik | rola |
|---|---|
| `run_all.sh` | sprawdza środowisko i Git LFS, uruchamia walidację, potem kampanię |
| `validate.py` | zgodność wszystkich implementacji, geometria C++ vs Python, 1 vs N wątków |
| `run_benchmark.sh` | kampania T1/T2/T4/T5, zbiera `raw.jsonl`, na końcu rysuje wykresy |
| `bench_filter.py`, `bench_chain.py`, `bench_efficiency.py` | pojedynczy pomiar (TEST 1–3) |
| `bench_common.py` | parser argumentów, fazy czasu, liczniki bajtów i RSS, rekord `BENCH` |
| `impl_rdf.py`, `impl_python.py`, `impl_uproot.py` | implementacje mierzonych operacji |
| `plot_results.py` | `raw.jsonl` → `bench.csv` + wykresy (nie wymaga ROOT-a, tylko matplotlib) |
| `slurm_benchmark.sbatch` | zadanie na Aresie (cały węzeł, `--exclusive`) |
| `environment.yml` | środowisko `pps-bench` (ROOT, correctionlib, uproot, awkward, matplotlib) |

## Dane

Seria `ds_xN` (N kopii `examples/test.root`, ZSTD:5, autoflush 10 000) musi już leżeć
w `$DATA_DIR`. Skrypt przerywa od razu, jeśli brakuje któregokolwiek pliku.

| plik | zdarzeń | klastrów | GB | rola |
|---|---:|---:|---:|---|
| `ds_x1` | 346 825 | 36 | 0.34 | T2 przy 1 wątku |
| `ds_x2` | 693 650 | 71 | 0.68 | T2 przy 2 wątkach |
| `ds_x4` | 1 387 300 | 140 | 1.35 | T2 przy 4 wątkach |
| `ds_x8` | 2 774 600 | 279 | 2.71 | T2 przy 8 wątkach |
| `ds_x16` | 5 549 200 | 556 | 5.41 | T2 przy 16 wątkach |
| `ds_x32` | 11 098 400 | 1111 | 10.84 | T2 przy 32 wątkach **oraz całe T1, T4 i T5** |

Klastrów na wątek jest w serii praktycznie stała liczba (36.0 … 34.7), a RDataFrame dzieli pracę
po klastrach, więc para (N wątków, `ds_xN`) daje uczciwe skalowanie słabe.

## Kampania

| | co zmienia | dataset | wątki | powtórki | biegów |
|---|---|---|---|---|---:|
| **T1** skalowanie silne | liczbę wątków przy stałym problemie | `ds_x32` | 1–48 | 3 | 81 |
| **T2** skalowanie słabe | problem i wątki naraz | `ds_xN` | N | 3 | 54 |
| **T4** struktura zapytania | lazy / eager / `Report()` × długość łańcucha 1, 3, 5 | `ds_x32` | 1 | 2 | 18 |
| **T5** implementacje | RDF / correctionlib / Python / uproot | `ds_x32` | 1 | 1 | 12 |

T3 (pamięć) nie ma własnych biegów: każdy bieg zapisuje `peak_rss_kb` i ślad
`rss_<label>.csv` próbkowany co 0.1 s.

Przed T1 wszystkie pliki serii są czytane w całości (`cat > /dev/null`), żeby pierwszy bieg na
każdym pliku nie płacił za zimny odczyt z Lustre.

Razem **165 biegów, ~1.2 h**. Najdroższy jest `chain/python` z T5 (~1100 s, ~11 GB RSS).
Każdy bieg ma limit `RUN_TIMEOUT` (2400 s); bieg, który go przekroczy albo się wywali, trafia do
`raw.jsonl` jako `"status": "failed"`.

Czas mierzony jest w fazach `setup`, `warmup`, `jit` i `loop`; porównywalna między
implementacjami jest tylko `loop`. Na `ds_x32` pętla jednowątkowa trwa 4–11 s przy 4–6 s kosztu
stałego, więc punkty T1 powyżej ~16 wątków mierzą głównie narzut per wątek (każdy wątek to
~250 MB RSS).

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

Datasety w `$SCRATCH/bench/data`. Potem:

```bash
DRY_RUN=1 DATA_DIR=$SCRATCH/bench/data ./test/run_benchmark.sh | tail -1   # liczba biegów
sbatch test/slurm_benchmark.sbatch
```

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
T1, T4 i T5 zawsze używają `ds_x32`, a ścieżka pythonowa materializuje całe kolumny (~11 GB
RSS), więc na laptopie z małą ilością RAM-u T5 wejdzie w swap.

## Wyniki

| plik | co pokazuje | test |
|---|---|---|
| `01_speedup_amdahl.png` | przyspieszenie vs wątki, dopasowanie Amdahla i USL | T1 |
| `02_parallel_efficiency.png` | efektywność równoległa [%] | T1 |
| `03_weak_scaling.png` | czas przy stałej pracy na wątek, przyspieszenie skalowane vs Gustafson | T2 |
| `04_rss_vs_threads.png` | koszt pamięciowy wątku | T3 |
| `05_rss_vs_size.png` | RSS wzdłuż serii słabej | T3 |
| `06_rss_over_time.png` | profil RSS w czasie, po krzywej na liczbę wątków | T3 |
| `07_query_structure.png` | liczba pętli po zdarzeniach i jej koszt | T4 |
| `08_implementations.png` | przepustowość i rozbicie na fazy | T5 |

Na konsolę trafiają też: frakcja szeregowa $s$ z Amdahla, $\sigma$ i $\kappa$ z USL,
przewidywane optimum liczby wątków i **zmierzony** udział setup + JIT przy jednym wątku. Jeśli
dopasowane $s$ jest wyraźnie większe od zmierzonego, degradacja ma przyczynę poza kodem
szeregowym i opisuje ją $\kappa$.

## Zmienne środowiskowe

| zmienna | domyślnie | znaczenie |
|---|---|---|
| `DATA_DIR` | `test/data` | katalog z `ds_xN.root` |
| `RESULTS` | `test/results` | katalog wyjściowy |
| `MACHINE` | `local` | trafia do każdego rekordu |
| `THREADS_LIST` | `1 2 4 8 12 16 24 32 48` | sweep wątków w T1 |
| `WEAK_SERIES` | `1 2 4 8 16 32` | pary (N wątków, `ds_xN`) w T2 |
| `CHAIN_LENS` | `1 3 5` | długości łańcucha w T4 |
| `REPEATS_STRONG` / `_WEAK` / `_QSTRUCT` / `_IMPL` | `3` / `3` / `2` / `1` | powtórzenia (mediana, wąsy min–max) |
| `RUN_TIMEOUT` | `2400` | limit na bieg [s] |
| `VALIDATE_THREADS` | `8` | liczba wątków w teście 1 vs N w `run_all.sh` |
| `SAMPLE_INTERVAL` | `0.1` | okres próbkowania RSS [s] |
| `DRY_RUN` | — | `1` wypisuje biegi bez uruchamiania |
| `PY` | `.venv/bin/python` lub `python3` | interpreter |

## Po zmianie geometrii lub kernela

`validate.py` porównuje wygenerowany C++ z `diamond_geometry.assign_region` na 100k punktów;
uruchom go po każdej zmianie w `POT_CONFIG` lub `get_cpp_source`. Cling nie pozwala
redefiniować funkcji w tym samym procesie, więc zmiany kernela sprawdzaj w świeżym procesie.
