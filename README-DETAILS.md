# Pi-on-Py Details

## Method

The benchmark computes a fixed number of digits of pi with Chudnovsky binary
splitting over 128 chunks by default. The work does not shrink when the machine
has more cores. Every tier verifies its result against `mpmath`; failed results
are excluded. Runs record repeated samples, median and best timings, variance,
CPU quota, affinity, steal time, interpreter, GMP details, and a result digest.

The tiers isolate these changes:

| Tier | What changes |
|---|---|
| `baseline` | Naive term-by-term series, one core |
| `algorithm` | Binary splitting, one core |
| `native` | Binary splitting plus GMP via `gmpy2`, one core |
| `parallel` | Binary splitting, all cores |
| `optimized` | GMP plus all cores |

This is an integer-arithmetic workload. It does not measure general SIMD,
floating-point, memory-bandwidth, branch, or I/O performance. The oracle uses
the same broad Chudnovsky family, so it is an independent implementation rather
than an algorithmically independent proof.

## Local Run

On a non-Azure machine:

```bash
python3 prepare_benchmark.py
python3 run_benchmark.py --sku azure_d2ps_v6
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
python3 run_benchmark.py --metric min_seconds
python3 run_benchmark.py --tiers baseline,optimized
```

Use the same `--size` on every machine being compared.

## Prices and Comparisons

`pricing.json` contains the monthly prices used by the report. Prices are inputs,
not measurements; update them for the region and billing term being studied.

To compare saved result files:

```bash
python3 compare_results.py results/
python3 compare_results.py results/ --baseline intel-box --markdown-out COMPARISON.md
```

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
