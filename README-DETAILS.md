# Pi-on-Py Details

## Method

The benchmark computes a fixed number of digits of pi with Chudnovsky binary
splitting over 128 chunks by default. The work does not shrink when the machine
has more cores. Every run verifies its result against `mpmath` and records
repeated samples, median and best timings, variance, CPU quota, affinity, steal
time, interpreter, GMP details, and a result digest.

The two modes isolate a single change:

| Mode | What changes |
|---|---|
| `generic` | Stock CPython big integers, all cores |
| `optimized` | GMP via `gmpy2` built for this CPU, all cores |

Both modes use the same algorithm, the same chunk decomposition, and the same
number of workers, so the difference between them is the native math library
alone.

This is an integer-arithmetic workload. It does not measure general SIMD,
floating-point, memory-bandwidth, branch, or I/O performance. The oracle uses
the same broad Chudnovsky family, so it is an independent implementation rather
than an algorithmically independent proof.

## Prerequisites

`prepare_benchmark.py` installs `gmpy2` with `--no-binary`, so it compiles
against the GMP on the machine rather than downloading a portable wheel with a
generic GMP bundled inside it. That build is what makes the optimized profile
architecture-specific, and it needs the GMP headers and a compiler:

```bash
sudo apt install -y python3-venv python3-dev libgmp-dev libmpfr-dev libmpc-dev build-essential
```

Only the machine running the optimized profile needs the GMP packages. If
`gmpy2` is ever installed from a portable wheel, the run reports
`generic prebuilt wheel` next to the mode and warns that the library is not
tuned for the CPU.

## Local Run

On a non-Azure machine:

```bash
python3 prepare_benchmark.py
python3 run_benchmark.py --cpu arm
```

If `gmpy2` fails to build, install the platform build dependencies and rerun:

```bash
sudo apt install -y python3-venv python3-dev libgmp-dev libmpfr-dev libmpc-dev build-essential
```

## Options

```bash
python3 run_benchmark.py --size quick
python3 run_benchmark.py --size standard
python3 run_benchmark.py --size deep
python3 run_benchmark.py --cpu arm
python3 run_benchmark.py --digits 500000
```

Use the same `--size` on every machine being compared.

`--cpu intel` selects the `generic` profile and `--cpu arm` selects the
`optimized` profile. To run a profile that does not match the host, for example
to measure the generic profile on ARM as a control, pass `--mode generic` or
`--mode optimized` directly; `--mode` overrides `--cpu` and skips the host
check. The `optimized` profile requires `gmpy2`, and stops with an error rather
than falling back to the generic backend.

## Prices and Comparisons

`pricing.json` contains the monthly prices used by the report. Prices are inputs,
not measurements; update them for the region and billing term being studied.

`--cpu intel` and `--cpu arm` each resolve to an entry via the `cpu_defaults`
map in `pricing.json`. Point those at different SKUs to price other VM sizes, or
pass `--price-per-month` / `--price-per-hour` to override the file entirely.

To compare saved result files:

```bash
python3 compare_results.py results/
python3 compare_results.py results/ --markdown-out COMPARISON.md
```

Every saved run is printed as one row.

## Troubleshooting

The Azure hook installs Python, GMP, compiler, and Git prerequisites during
`azd up`. For an existing VM, rerun the hook from the repository checkout:

```bash
./scripts/deploy-to-vms.sh
```

Run the benchmark as `azureuser`, not `root`, so the virtual environment and
results belong to the login account. On Ubuntu, a missing virtual environment
support package can be repaired with:

```bash
sudo apt install -y python3-venv
```

`azd down` deletes the resource group and all resources in it, including the VMs,
disks, VNet, and Bastion.

## License

MIT. See [LICENSE](LICENSE).
