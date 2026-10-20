# Wyniki

Każdy katalog z wynikami ma `raw.jsonl` (rekord na bieg), `bench.csv` i wykresy z
`test/plot_results.py`. Wszystkie wejścia są czytane z dysku po wyrzuceniu z page cache.

Na Heliosie wszędzie biegnie łańcuch 11 filtrów (10 gałęzi, `bench_chain.py --chain long`,
test `chain11`), na jednym zbiorze ~1 TB na raz. Pełne pliki to ~1 TB na dysku, z którego pętla
czyta kilka procent; slim to 1,5 TB czytane w całości.

| katalog | maszyna | dane | łańcuch | biegi | w pracy | stan |
|---|---|---|---|---|---|---|
| `single-core-ares/` | Ares, 1 rdzeń (`taskset`) | 1–9 kopii `ds_x32` (11,1–99,9 mln zdarzeń), pełne pliki, ZSTD:5 | 5 filtrów, filtr, efektywność | seria rozmiarów RDF / uproot / Python, struktura zapytania na 9 kopiach | `bench_implementations_100m` (przepustowość, fazy czasu, szczyt pamięci na 99,9 mln zdarzeń), tabela query structure | jest |
| `synthetic-slim/` | Helios | 96 plików slim (10 gałęzi), 29,8 mld zdarzeń, 1,54 TB | 11 filtrów | T1 1–192 (96–192: 2–4 biegi), T2 1–96 | krzywa slim na rysunku skalowania (`bench_full_files`), `bench_scalability_slim.tex`, `bench_weak_slim`; kolumna slim w tabeli zbiorów | jest |
| `full-chain11/artificial-1tb/` | Helios | 96 kopii `ds_x32`, pełne pliki (1984 gałęzie), 1,07 mld zdarzeń, 1,04 TB | 11 filtrów | T1 1–192, 96–192 trzy razy | nieużywane w pracy: dawny test pamięci (blok M, `plot_memory_control.py`), usunięty z pracy; 5 mln koszyków na plik (10–30× więcej niż dane rzeczywiste) zawyża koszt wątku | jest |
| `full-chain11/run2-1tb/` | Helios | Run 2 Open Data (Run2016H, G), 653 pliki, 1,05 mld zdarzeń, 1,04 TB, LZMA:9 | 11 filtrów, `--period 2016` z cięciami x/y (przepuszcza 1,43%, 14,9 mln) | krok R kampanii `slurm_final.sbatch`: T1 1–192, 80–192 trzy razy | rysunek pełnych plików, tabela zbiorów; czas pętli to najszybszy z trzech biegów (`--best-of`): od 112 wątków powtórki rozpadają się na 12,5–15,3 s (89–101 zajętych rdzeni) i 16–26 s (57–78), także bez żadnego kopiowania, bo pętla jest krótka, a Lustre współdzielony | jest |
| `run3/chain11/` | Helios | Run 3 `core.txt`: 2488 plików z er Run2024C–Run2026D (każdy czytelny plik z kolumnami łańcucha), 1,31 mld zdarzeń, 1,80 TB, LZMA:9 | 11 filtrów, cięcia Run 3 (`PERIODS["run3"]`, `test/README.md`, „Cięcia Run 3”), przepuszcza 37,1% | J1: T1 1–192, 80–192 trzy razy | rysunek pełnych plików, tabela zbiorów | jest |
| `run3/node/` | Helios | Run 3 `core.txt`, cały zbiór | 11 filtrów, cięcia Run 3 | J3: RDF na 192 wątkach i `uproot-pool` na 192 procesach; J4: `python-pool` na 192 procesach; pule dostają kawałki po 250 000 zdarzeń (6644 zadania); po 3 biegi | `17_whole_node.png`, `table_whole_node.tex` (sekcja Comparison of Implementations: Whole Node) | jest |
| `comparison/` | — | z katalogów powyżej | — | — | `full_files_chain11.png` i `sets_summary.{csv,tex}` (Run 2, Run 3, slim); `memory_control.{png,csv}` nieużywane w pracy | jest |
| `archive/` | — | kampanie, które nie idą do pracy | — | — | — | — |

`archive/`:

| katalog | co to jest | dlaczego poza pracą |
|---|---|---|
| `chain5/helios-full/` | pełne kopie `ds_x32`, 11 M / 100 M / 355 M / 1 TB, filtr, łańcuch 5 filtrów, efektywność, T1 do 192 (`full-1tb` = scalone `full-1tb-job1` i `-job2`) | łańcuch 5 filtrów; zastępuje go `full-chain11/artificial-1tb` |
| `chain5/run2-opendata/` | Open Data 89 M / 356 M / 1 TB, łańcuch 5 filtrów `--period 2016` | jak wyżej; zastępuje go `full-chain11/run2-1tb` |
| `chain5/control-1tb/` | punkty kontrolne na kopiach `ds_x32` obok Open Data | jak wyżej |
| `chain5/memtest/` | 384 × `ds_x32_head.root` (1/10 koszyków), z page cache | test układu pliku (koszyki vs gałęzie) |
| `chain5/layout/` | `14_optimum_vs_size.png`, `16_memory_layout.png`, `summary_memory_layout.csv` | rysunki z łańcucha 5 filtrów; z `16_*`: koszt wątku rośnie z koszykami na plik (`ds_x32` ~5 mln, Open Data ~0,5 mln) |
| `run3-cuts2026/` | J1 (`chain11/`: r1 1–192 wątki, r2 32–192 na drugim węźle) i J2 (`chain11-weak/`) na Run 3 z cięciami 2026, czyli z próbki `examples/test.root` (RP 22, pary 23\|123 i 3\|103) | cięcia nie pasują do er 2024F–2026D: przepuszczają 10,8%, w kilku erach prawie nic, a praca dalszych filtrów zależy od tego, ile zdarzeń do nich dochodzi; zastępują je pomiary z cięciami Run 3. Zostaje jako kontrola: te same pliki przy innej selekcji pokazują, czy selektywność zmienia kształt skalowania |
| `run2-timecuts/` | krok R na Run 2 Open Data z cięciami 2016 na czas toru (`time`, `timeUnc`), przepuszczał 1,9% (20,2 mln); powtórki od 112 wątków mierzone w czasie kopiowania Run 3 na ten sam Lustre | paski PPS z 2016 nie mierzą czasu, więc cięcia na czas nie pasowały do tych danych; zastąpiony przez `full-chain11/run2-1tb` z cięciami x/y |
| `run2-nopass/` | pierwszy krok R na Run 2 Open Data, cięcia 2016 sprzed poprawki, z cięciami torów z 2026 (`single_rp_idx == -1`, `time != 0`, `time_unc != 0`), których tory paskowe nie spełniają | łańcuch nie przepuścił żadnego zdarzenia, więc mierzył tylko filtry do pierwszego pustego; zastąpiony przez `full-chain11/run2-1tb` |
| `slim11-r5r6/` | zbiór slim jak `synthetic-slim/` plus trzecia dogrywka r5, r6 | sesja r5/r6 była w całości zakłócona przez Lustre (112 wątków: 1082 i 965 s wobec 416 s), pominięta |
| `ares-10gb-cached/` | dawna kampania 10 GB z page cache | nieużywana w pracy |

Wyniki ostatecznej kampanii (`test/slurm_final.sbatch`, październik 2026) są w
`full-chain11/run2-1tb/`, `run3/chain11/` i `run3/node/`, przepływ po erach z bramek obok nich
(`run2_chain11_gate.txt`, `run3_chain11_gate.txt`), a log kroków w `run3/final_progress.log`.

Wykresy katalogów, z `table_whole_node.tex` (blok N) w `run3/node/` i `08_implementations.png`
(blok A) w `single-core-ares/`:

```bash
for d in results/single-core-ares results/run3/chain11 results/run3/node results/full-chain11/run2-1tb; do
    python test/plot_results.py --results "$d"
done
```

Rysunki i tabele porównania:

```bash
python test/plot_real_vs_synthetic.py --out results/comparison \
    --set "results/full-chain11/run2-1tb:chain11:Run 2 Open Data" \
    --set "results/run3/chain11:chain11:Run 3" \
    --set "results/synthetic-slim:chain11:artificial, slim files" \
    --best-of "Run 2 Open Data"

python test/plot_memory_control.py --out results/comparison \
    --set "results/full-chain11/artificial-1tb:chain11:artificial, full files" \
    --set "results/synthetic-slim:chain11:artificial, slim files" \
    --profile "artificial, full files" --files "artificial, full files:96"
```

Zbiory, których katalogu jeszcze nie ma, skrypt pomija z ostrzeżeniem. `--best-of` bierze dla
danego zbioru najszybszy bieg w każdym punkcie zamiast mediany i oznacza go `*` w tabeli.

`plot_memory_control.py` rysuje szczyt RSS, RSS z końca pętli (maksimum z ostatnich 10% fazy
`loop` w `rss_*.csv`) i RSS w czasie pętli. `--files LABEL:N` dopasowuje RSS z końca pętli do
`max(T, min(2T, N))` otwartych drzew: na kopiach 157 MB na drzewo, rms 0,2 GB (prosta w T:
1,9 GB). Slim ma tylko szczyt, bo sampler tamtej kampanii nie zbierał próbek w czasie pętli.

`plot_memory_control.py` (blok M) nie idzie już do pracy; zostaje do odtworzenia dawnego testu.

Do pracy (rysunki `fig:bench_implementations_100m`, `fig:bench_full_files`, `fig:bench_whole_node`
i tabele `tab:sets_summary`, `tab:whole_node`):

```bash
cp results/single-core-ares/08_implementations.png doc/Images/bench_implementations_100m.png
cp results/comparison/full_files_chain11.png doc/Images/bench_full_files.png
cp results/comparison/sets_summary.tex doc/Tables/sets_summary.tex
cp results/run3/node/17_whole_node.png doc/Images/bench_whole_node.png
cp results/run3/node/table_whole_node.tex doc/Tables/whole_node.tex
```

W bloku N pula `uproot` przekazała przez `read()` 4,3 TB i przeczytała z dysku 1,69 TB, choć sama
zamówiła 90,8 GB koszyków (`io_rchar_loop`, `io_read_bytes_loop` wobec `bytes_loop`). uproot 5.7
czyta pliki lokalne przez `fsspec`, czyli pythonowy obiekt pliku z domyślnym buforem, a Python
dobiera bufor do `st_blksize` systemu plików. Na jednym pliku Run 3 lokalnie: bufor 128 kB daje
2,4× zamówionych bajtów, 1 MB 12,7×, 4 MB 50× (na Heliosie 47×), 16 MB 192×. Rozmiar bloku na
Heliosie: `stat -c %o <plik .root>`.
