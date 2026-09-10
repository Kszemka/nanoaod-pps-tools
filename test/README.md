# Uruchomienie benchmarku na Ares / Helios

Co jest mierzone i dlaczego — patrz [TESTING.md](TESTING.md). Ten plik opisuje wyłącznie
uruchomienie.

## Szybki start lokalnie

macOS nie ma GNU `time` ani `timeout`; bez nich odpadają peak RSS z `/usr/bin/time -v`, CPU%
i twardy limit na bieg (zostaje tylko `getrusage`). Warto je doinstalować:

```bash
brew install coreutils gnu-time     # daje gtime i gtimeout
```

```bash
cd test
python validate.py --max-events 40000     # poprawność przed jakimkolwiek pomiarem
./run_benchmark.sh quick                  # smoke test na examples/test.root
python plot_results.py
```

Skrypty same wybierają `.venv/bin/python` z korzenia repo, jeśli istnieje, i od razu sprawdzają,
czy ten interpreter widzi ROOT. Wywołania pythonowe wprost (`validate.py`, `plot_results.py`)
uruchamiaj przez `.venv/bin/python`, chyba że masz aktywne środowisko — `python3` z `PATH` to
zwykle inny interpreter, bez PyROOT. Innym interpreterem sterujesz przez `PY=...`.

### Profil laptopowy

Domyślne wartości celują w węzeł obliczeniowy (48–192 rdzeni, 192+ GB RAM). Na laptopie trzeba
zejść z liczbą wątków i z rozmiarem danych — ścieżka pythonowa materializuje całe kolumny
w pamięci, więc to ona, a nie RDataFrame, wyznacza górny limit:

```bash
export THREADS_LIST="1 2 4 8 16"     # nie więcej niż rdzeni
export SCALE_SERIES="1 2 4 8"        # ~2.5 GB danych, Python mieści się w RAM
export DS_L=$PWD/test/data/ds_x8.root
export REPEATS=2
```

Przy 24 GB RAM seria powyżej `x8` zaczyna wchodzić w swap na ścieżce pythonowej — pomiar czasu
staje się wtedy pomiarem dysku. `gtimeout` jest tu zabezpieczeniem, nie ozdobą.

## Krok po kroku na Cyfronecie

### 1. Logowanie i katalog roboczy

```bash
ssh <login>@ares.cyfronet.pl        # lub helios.cyfronet.pl
mkdir -p $SCRATCH/bench && cd $SCRATCH/bench
```

`$SCRATCH` jest czyszczony po ~30 dniach — gotowe wyniki skopiuj do
`$PLG_GROUPS_STORAGE/<grant>/`. `$HOME` ma limit ~10 GB, więc **nie** instaluj tam
środowiska.

### 2. Środowisko

Moduły Cyfronetu mają ROOT, ale nie mają `correctionlib`, więc potrzebne jest własne
środowisko:

```bash
cd $SCRATCH/bench
curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba
mkdir -p micromamba && mv bin micromamba/
export MAMBA_ROOT_PREFIX=$SCRATCH/bench/micromamba
eval "$(./micromamba/bin/micromamba shell hook -s bash)"

git clone <repo-url> nanoaod-pps-tools
micromamba env create -f nanoaod-pps-tools/test/environment.yml
micromamba activate pps-bench
```

### 2b. Git LFS

`examples/test.root` jest trzymany w Git LFS. Bez `git-lfs` klon daje w tym miejscu
134-bajtowy plik tekstowy ze wskaźnikiem zamiast 240 MB danych, a wszystko dalej wywala się
na nieczytelnym pliku ROOT. `environment.yml` instaluje `git-lfs`, więc po aktywacji
środowiska wystarczy:

```bash
cd $SCRATCH/bench/nanoaod-pps-tools
git lfs install
git lfs pull
ls -la examples/test.root        # ma mieć ~240 MB, nie 134 B
```

`run_all.sh` sprawdza to sam i przerywa z czytelnym komunikatem, jeśli trafi na wskaźnik.

Alternatywa, jeśli LFS sprawia kłopoty: skopiuj plik wprost z laptopa —
`scp examples/test.root <login>@ares.cyfronet.pl:'$SCRATCH'/bench/nanoaod-pps-tools/examples/`.

Sprawdzenie: `python -c "import ROOT, correctionlib, numpy; print(ROOT.gROOT.GetVersion())"`.

### 3. Dane

Kopie pliku źródłowego. `--autoflush` steruje liczbą klastrów TTree — **to on, a nie rozmiar
pliku, wyznacza górną granicę sensownego zrównoleglenia** (RDataFrame dzieli pracę po
klastrach, nie po zdarzeniach). Skrypt sam ostrzega, jeśli klastrów jest za mało.

```bash
cd $SCRATCH/bench/nanoaod-pps-tools
mkdir -p $SCRATCH/bench/data

# S = plik źródłowy bez zmian; kopia 1:1 przez Snapshot tylko przekodowałaby te same dane.
cp examples/test.root $SCRATCH/bench/data/ds_s.root

python test/make_dataset.py --out $SCRATCH/bench/data/ds_m.root  --copies 8   --autoflush 10000
python test/make_dataset.py --out $SCRATCH/bench/data/ds_l.root  --copies 40  --autoflush 15000
python test/make_dataset.py --out $SCRATCH/bench/data/ds_xl.root --copies 100 --autoflush 15000

for n in 1 2 4 8 16 32 64; do
    python test/make_dataset.py --out $SCRATCH/bench/data/ds_x${n}.root --copies $n --autoflush 10000
done
```

Albo jednym poleceniem: `DATA_DIR=$SCRATCH/bench/data ./test/make_all_datasets.sh`.

`ds_x1` jest generowany mimo że `ds_s` to ten sam plik — seria rozmiarowa musi mieć jednakowy
`autoflush` we wszystkich punktach, inaczej klastrowanie stałoby się ukrytą drugą zmienną
i pierwszy punkt odstawałby od dopasowanej prostej.

Razem ~60 GB. Liczby zdarzeń, klastrów i bajtów per gałąź lądują w
`$SCRATCH/bench/data/dataset_info.json` — `plot_results.py` czyta stamtąd limit klastrów,
żeby nanieść go na wykres skalowania.

Kopiowanie pliku zwiększa rozmiar o ~20% względem `N × źródło`, bo mniejsze klastry gorzej się
kompresują. Kompresja jest dopasowywana do pliku źródłowego automatycznie.

**Czas generacji.** Domyślne dopasowanie kompresji do źródła jest wierne, ale jeśli źródło
używa LZMA, zapis jest bardzo wolny — `ds_xl` potrafi zająć godziny. Generuj datasety
oddzielnym, długim zadaniem (nie w tym samym, co pomiary), np.:

```bash
sbatch -A <GRANT>-cpu -p plgrid-long -N1 -c8 --time=12:00:00 \
       --wrap "micromamba run -n pps-bench bash test/make_all_datasets.sh"
```

Alternatywa: `--compression 5:5` (ZSTD zamiast LZMA) skraca generację wielokrotnie. **Zmienia
jednak koszt dekompresji, czyli jedną z mierzonych wielkości** — jeśli jej użyjesz, użyj jej dla
*wszystkich* datasetów w serii i odnotuj to w opisie wyników. Nigdy nie mieszaj algorytmów
kompresji w obrębie jednego wykresu.

### 4. Test dymny na węźle obliczeniowym

Jako zadanie wsadowe, nie przez `srun --pty`: zerwane połączenie SSH zabija sesję
interaktywną razem z biegiem, a zakolejkowane zadanie liczy się dalej i zapisuje wyjście
do pliku.

```bash
cd $SCRATCH/bench/nanoaod-pps-tools
sed -i "s/<GRANT>/twoj-grant/" test/slurm_smoke.sbatch
mkdir -p $SCRATCH/bench/logs
sbatch --output=$SCRATCH/bench/logs/smoke-%j.out \
       --error=$SCRATCH/bench/logs/smoke-%j.err \
       test/slurm_smoke.sbatch

squeue -u $USER                              # postęp
tail -f $SCRATCH/bench/logs/smoke-<jobid>.out
```

Ścieżek `$SCRATCH` nie da się użyć w dyrektywach `#SBATCH` (są czytane przed rozwinięciem
zmiennych powłoki), dlatego katalog logów podaje się w wierszu poleceń. Bez tego pliki
`smoke-<jobid>.out` lądują w katalogu, z którego wywołano `sbatch`.

Zadanie ma się skończyć linią `RESULT: all checks passed` i wypisaniem `bench.csv`.
Jeśli walidacja nie przechodzi, nie uruchamiaj pomiarów — żadna liczba nie będzie wtedy
nic warta.

Jeśli mimo wszystko wolisz sesję interaktywną, uruchom ją w `tmux`, żeby przeżyła
rozłączenie:

```bash
tmux new -s bench
srun -A <GRANT>-cpu -p plgrid-testing -N1 -n1 -c4 --time=0:30:00 --pty bash -l
# Ctrl-b d odłącza, `tmux attach -t bench` wraca
```

Warto też ograniczyć same rozłączenia — na laptopie w `~/.ssh/config`:

```
Host ares.cyfronet.pl
    ServerAliveInterval 60
    ServerAliveCountMax 10
```

### 5. Pełny bieg

Uzupełnij `<GRANT>` i partycję w plikach sbatch, a dla Heliosa dodatkowo `--cpus-per-task`
(patrz komentarz na górze pliku — specyfikację trzeba potwierdzić w aktualnej dokumentacji).

```bash
sbatch test/slurm_benchmark.sbatch           # Ares
sbatch test/slurm_benchmark_helios.sbatch    # Helios
```

`--exclusive` jest w obu skryptach celowo: na współdzielonym węźle wykres skalowania mierzy
obciążenie sąsiadów, nie własny kod.

### 6. Kontrola i odbiór wyników

```bash
sacct -j <jobid> --format=JobID,JobName,State,Elapsed,MaxRSS,AveCPU,NCPUS,ReqMem
```

(`seff` nie jest zainstalowany na Aresie.)

`MaxRSS` z `sacct` powinien zgadzać się z kolumną `time_maxrss_kb` w `results/bench.csv` —
to niezależne potwierdzenie, że pomiar pamięci jest poprawny.

```bash
cp -r $SCRATCH/bench/results-* $PLG_GROUPS_STORAGE/<grant>/
scp -r <login>@ares.cyfronet.pl:$PLG_GROUPS_STORAGE/<grant>/results-ares .
```

Wykresy z obu maszyn razem:

```bash
mkdir -p combined && cat results-ares/raw.jsonl results-helios/raw.jsonl > combined/raw.jsonl
cp results-ares/dataset_info.json combined/
python test/plot_results.py --results combined
```

## Zmienne środowiskowe

| zmienna | domyślnie | znaczenie |
|---|---|---|
| `MACHINE` | `local` | trafia do każdego rekordu; rozróżnia Ares od Heliosa na wykresach |
| `DATA_DIR` | `test/data` | katalog z datasetami |
| `RESULTS` | `test/results` | katalog wyjściowy |
| `THREADS_LIST` | `1 2 4 8 16 32 48` | sweep wątków |
| `REPEATS` | `3` | powtórzenia (raportowana mediana) |
| `RUN_TIMEOUT` | `300` | twardy limit na pojedynczy bieg |
| `PY` | `python3` | interpreter |

Bieg, który przekroczy `RUN_TIMEOUT`, jest zapisywany jako `"status": "failed"`, a nie
pomijany — granica wydajności implementacji też jest wynikiem i ma być widoczna w danych.

## Po zmianie geometrii lub kernela

`validate.py` porównuje wygenerowany C++ z `diamond_geometry.assign_region` na 100k punktów.
To jedyne zabezpieczenie przed cichym błędem transkrypcji geometrii — uruchom je po każdej
zmianie w `POT_CONFIG` lub w `get_cpp_source`.

Uwaga: cling nie pozwala redefiniować raz zadeklarowanej funkcji w tym samym procesie.
Zmiany w kernelu weryfikuj w świeżym procesie, nie przez ponowne uruchomienie komórki
w żywym kernelu notebooka.
