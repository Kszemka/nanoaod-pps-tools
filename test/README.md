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

Diagnostyka I/O osobno — mówi nie „ile bajtów", ale dlaczego tyle (liczba wywołań read,
bajty odczytane ponad to, o co poproszono, sweep rozmiaru `TTreeCache`):

```bash
python diag_io.py --input ../examples/test.root --cache-mb 0 30 128
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
export DS_MAIN=$PWD/test/data/ds_x8.root
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

Sprawdzenie:
`python -c "import ROOT, correctionlib, numpy, uproot, awkward; print(ROOT.gROOT.GetVersion())"`.

`uproot` i `awkward` nie są opcjonalne. Na nich stoi implementacja `uproot` — jedyna
porządnie kolumnowa ścieżka pythonowa w tym benchmarku. Bez niej stronę pythonową
reprezentuje tylko `AsNumpy`, którego koszt jest zdominowany przez to, że PyROOT tworzy
jeden obiekt na zdarzenie, więc główny stosunek RDataFrame-do-Pythona mierzyłby nie to, co
powinien (8.66 s vs 0.21 s na tym samym zapytaniu). `run_all.sh` przerywa, jeśli ich brak.

### 3. Dane

Kopie pliku źródłowego. `--autoflush` steruje liczbą klastrów TTree — **to on, a nie rozmiar
pliku, wyznacza górną granicę sensownego zrównoleglenia** (RDataFrame dzieli pracę po
klastrach, nie po zdarzeniach). Skrypt sam ostrzega, jeśli klastrów jest za mało.

Najprościej jednym poleceniem, bo skrypt generuje też warianty kontrolne i konwersję do
RNTuple, a każdy plik od razu opisuje w `dataset_info.json`:

```bash
cd $SCRATCH/bench/nanoaod-pps-tools
DATA_DIR=$SCRATCH/bench/data ./test/make_all_datasets.sh
```

Co powstaje i po co:

| plik | kopii | autoflush | rola |
|---|---|---|---|
| `ds_s` | 1 | (źródło) | kopia pliku źródłowego, LZMA:9 — tylko referencja |
| `ds_x1 … ds_x32` | 1–32 | 10 000 | seria „vs rozmiar"; `ds_x1` = ścieżki jednowątkowe, `ds_x8` = **główny dataset** |
| `ds_x8_coarse` | 8 | 250 000 | kontrola klastrowania — ta sama liczba zdarzeń, 25× większe klastry |
| `ds_x8_slim` | 8 | 10 000 | kontrola amplifikacji odczytu — 10 gałęzi zamiast 1984 |
| `ds_x8_rntuple` | 8 | — | konwersja `ds_x8` na RNTuple (`make_rntuple.py`) |
| `ds_l` | 40 | 15 000 | **tylko** dla `diag_io.py` — patrz niżej |

**`ds_l` nie bierze udziału w pomiarach czasu i nie powinien.** Zmierzone na Aresie: 36 biegów
przez 1.77 h, z czego 11 weszło w timeout i nie dało żadnego rekordu (0.92 h, ponad połowa
zadania). W biegach, które się skończyły, dominował koszt stały, nie pętla zdarzeń —
`efficiency/jit` to 290 s, z czego 202 s setupu i 84 s pętli. Godziny kupiły więc głównie
narzut, a przy jednej powtórce zamiast trzech nie ma z czego liczyć rozrzutu. `SCALE_SERIES`
kończy się na 32 kopiach, więc `ds_l` nie jest też punktem serii rozmiarowej.

Zostaje w generacji z jednego powodu: to jedyny plik, na którym pojawia się anomalia odczytu
10 GB, a `run_all.sh` puszcza na nim `diag_io.py` — diagnostykę tylko do odczytu, liczoną
w sekundach. Jeśli nie zamierzasz jej używać, pomiń go: `SERIES="1 2 4 8 16 32" ` i tak
zbuduje wszystko, co mierzy kampania.

`ds_x1` jest generowany mimo że `ds_s` to ten sam plik — seria rozmiarowa musi mieć jednakowy
`autoflush` we wszystkich punktach, inaczej klastrowanie stałoby się ukrytą drugą zmienną
i pierwszy punkt odstawałby od dopasowanej prostej. `ds_x1` służy też ścieżkom
jednowątkowym, żeby biegły na tej samej kompresji co RDataFrame.

Para `ds_x8` / `ds_x8_coarse` musi mieć **identyczną liczbę zdarzeń** — inaczej objętość
udawałaby klastrowanie, czyli dokładnie to zakłócenie, które ta kontrola ma wykluczyć.
`run_benchmark.sh` sprawdza to i odmawia uruchomienia porównania, jeśli się różnią.

Liczby zdarzeń, klastrów, bajtów i rozmiarów koszyka per gałąź lądują w
`$SCRATCH/bench/data/dataset_info.json` — `plot_results.py` czyta stamtąd limit klastrów dla
**użytego** datasetu, żeby nanieść go na wykres skalowania. Dataset bez wpisu jest błędem
przerywającym pomiar: bez niego limit wątków i adnotacje brałyby liczby z innego pliku.

Kopiowanie pliku zwiększa rozmiar o ~20% względem `N × źródło`, bo mniejsze klastry gorzej się
kompresują. Kompresja jest dopasowywana do pliku źródłowego automatycznie.

**Czas generacji.** `make_all_datasets.sh` wymusza ZSTD:5 właśnie dlatego: przy LZMA:9 ze
źródła zapis jednej kopii zajmuje 156 s zamiast 70 s, więc cała seria potrafi zająć godziny.
Generuj datasety oddzielnym, długim zadaniem (nie w tym samym, co pomiary), np.:

`Snapshot` jest jednowątkowy, więc domyślny bieg zostawia 47 z 48 rdzeni bezczynnych na
godziny. Pliki są od siebie niezależne, więc `JOBS=N` buduje po N naraz i całość trwa tyle,
ile jej największy element, a nie tyle, ile ich suma:

```bash
JOBS=6 DATA_DIR=$SCRATCH/bench/data ./test/make_all_datasets.sh
```

Każdy bieg ma wtedy własny log w `$DATA_DIR/logs/`, bo sześć przeplecionych strumieni jest
nieczytelne dokładnie wtedy, gdy coś się wywali. Skrypt czeka na wszystkie przed konwersją
RNTuple (ta potrzebuje kompletnego `ds_x8`) i przerywa, jeśli którykolwiek build zawiódł.

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

Najpierw sprawdź, na co idą godziny grantu — `DRY_RUN` wypisuje każdy bieg, nie uruchamiając
żadnego. Liczby biegów nie da się policzyć z lektury skryptu, bo sweep wątków jest przycinany
w trakcie do liczby klastrów datasetu, a całe bloki są pomijane przy braku pliku:

```bash
DRY_RUN=1 ./test/run_benchmark.sh full | tail -3          # budżet: załóż, że wszystko istnieje
DRY_RUN=have ./test/run_benchmark.sh full | grep SKIP     # co wypadnie przy brakach na dysku
```

Drugi tryb jest ważniejszy przy niekompletnym zestawie danych. Bloki `clusters`, `layout`
i `rntuple` **pomijają się po cichu**, jeśli brakuje ich pliku kontrolnego — bieg kończy się
sukcesem, tylko bez trzech eksperymentów. To właśnie te trzy odpowiadają na otwarte pytanie
o odczyt, więc warto wiedzieć zawczasu, że nie wystartują.

Na domyślnej konfiguracji to **250 biegów**. Zmierzone czasy z poprzedniej kampanii na tym
samym rozmiarze (2.77 mln zdarzeń) dają **~1–1.5 h**, przy limicie 8 h w pliku sbatch:
ścieżki RDataFrame to 6–14 s na bieg, a najdroższy element to `chain/python` w serii
rozmiarowej (276 s na `ds_x8`, a na `ds_x16` i `ds_x32` z założenia wchodzi w timeout i trafia
na wykres jako dolne ograniczenie).

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
cp results-*/rss_*.csv combined/        # wykres profilu pamięci czyta je z katalogu wyników
python test/plot_results.py --results combined
```

Scalanie jest bezpieczne tylko w obrębie tej samej wersji schematu. Każdy rekord nosi
`schema_version`, a `plot_results.py` odrzuca starsze i mówi ile — część pól zmieniła
znaczenie (`n_events` w TEŚCIE 3, podział czasu między fazy), więc uśrednienie rekordów
z dwóch wersji dałoby liczby nienależące do żadnej z nich.

## Zmienne środowiskowe

| zmienna | domyślnie | znaczenie |
|---|---|---|
| `MACHINE` | `local` | trafia do każdego rekordu; rozróżnia Ares od Heliosa na wykresach |
| `DATA_DIR` | `test/data` | katalog z datasetami |
| `RESULTS` | `test/results` | katalog wyjściowy |
| `THREADS_LIST` | `1 2 4 8 16 32 48` | sweep wątków |
| `REPEATS` | `3` | powtórzenia (raportowana mediana, wąsy min–max) |
| `RUN_TIMEOUT` | `300` | twardy limit na pojedynczy bieg |
| `DS_MAIN` | `$DATA_DIR/ds_x8.root` | główny dataset sweepów (`DS_L` działa jako alias) |
| `DS_S` | `$DATA_DIR/ds_x1.root` | dataset ścieżek jednowątkowych |
| `DS_COARSE` | `$DATA_DIR/ds_x8_coarse.root` | druga połowa pary kontrolnej klastrowania |
| `BENCH_INPUT` | — | tryb jednego datasetu: wszystkie testy na tym pliku, seria pominięta |
| `DRY_RUN` | — | `1` = wypisz plan zakładając, że wszystkie datasety istnieją; `have` = tylko to, co pozwalają pliki na dysku |
| `WANT_DS_L` | `1` | `0` pomija generację `ds_l` (40 kopii, ~11 GB, tylko dla `diag_io.py`) |
| `JOBS` | `1` | ile datasetów generować równolegle (`make_all_datasets.sh`) |
| `SERIES` | `1 2 4 8 16 32` | liczby kopii w serii rozmiarowej |
| `SAMPLE_INTERVAL` | `0.1` | okres próbkowania RSS (sekundy) |
| `PY` | `python3` | interpreter |

Bieg, który przekroczy `RUN_TIMEOUT`, jest zapisywany jako `"status": "failed"` wraz
z wartością limitu, a `plot_results.py` **rysuje go jako dolne ograniczenie** — granica
wydajności implementacji też jest wynikiem i ma być widoczna na wykresie, nie tylko w danych.

Profil pamięci (`rss_<label>.csv`) próbkuje **sam proces mierzony**, przez wątek daemon
czytający `/proc/self/statm`. Wcześniej próbkował go bash przez `ps -p $!`, ale komenda jest
owinięta w `timeout` i `/usr/bin/time`, więc `$!` było pidem opakowania: wszystkie zebrane tak
ślady to płaska linia na poziomie ~1.1 MB, czyli rozmiar samego `timeout`.

## Po zmianie geometrii lub kernela

`validate.py` porównuje wygenerowany C++ z `diamond_geometry.assign_region` na 100k punktów.
To jedyne zabezpieczenie przed cichym błędem transkrypcji geometrii — uruchom je po każdej
zmianie w `POT_CONFIG` lub w `get_cpp_source`.

Uwaga: cling nie pozwala redefiniować raz zadeklarowanej funkcji w tym samym procesie.
Zmiany w kernelu weryfikuj w świeżym procesie, nie przez ponowne uruchomienie komórki
w żywym kernelu notebooka.
