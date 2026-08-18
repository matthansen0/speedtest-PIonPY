# SpeedTest: Pi-on-Py

<p align="center">
	<img src="media/pionpy.png" alt="Pi on Py" title="Pi on Py" width="400"/>
</p>

This project validates the cost performance of ARM compute by optimizing specific
workloads and measuring the result against x86. It asks a practical migration
question: does an ARM VM deliver enough performance per dollar for this workload
to justify using it?

The current workload is big-integer computation of pi. The benchmark keeps the
work fixed, applies distinct algorithmic, native-library, and parallel
optimizations, verifies the output, and reports performance as cost per unit of
work. The same approach can be extended with workloads that exercise other CPU
behaviors.

## Method

Every machine performs the same fixed amount of work: a set number of digits of
pi, computed by the same algorithm, saturating every usable core. Only the
big-integer backend changes:

| Mode | Backend |
|---|---|
| `generic` | Stock CPython integers, no native math library |
| `optimized` | GMP via `gmpy2`, compiled for the target CPU |

Both modes run in parallel across all cores, so the single variable is whether
the numeric stack is tuned for the architecture. Each result is verified against
an independent `mpmath` calculation, and timings are repeated to a wall-clock
budget instead of taken from one sample.

## Comparison Model

Run `generic` on the x86 machine to represent the status quo: stock libraries,
no optimization effort. Run `optimized` on the ARM machine to represent the
migration target after effort has been spent on it. Both compute identical
digits, so the results are directly comparable.

Running both modes on both machines is also supported, and is the way to tell
whether a difference came from the architecture or from the optimization.

## Deploy

```bash
azd auth login --use-device-code
az login --use-device-code
git clone https://github.com/matthansen0/speedtest-PIonPY
cd speedtest-PionPY
azd env new pionpy --location centralus
azd env set ADMIN_PASSWORD 'choose-a-strong-password'
azd up
```

In the Azure Portal, open `pionpy-bastion`, choose **Connect > Bastion**, select
a VM, and sign in as `azureuser` with the password.

## Run

On each VM:

```bash
sudo apt update
sudo apt install -y git python3-venv python3-dev \
    libgmp-dev libmpfr-dev libmpc-dev build-essential
git clone https://github.com/matthansen0/speedtest-PIonPY
cd speedtest-PIonPY
python3 prepare_benchmark.py
```

The GMP packages are only strictly required on the Arm VM, which builds `gmpy2`
against them for the optimized profile. The Intel VM needs just `git`,
`python3-venv` and `python3-dev` for the stock profile. Installing the same list
on both is simplest, and lets either machine run either profile.

Intel VM:

```bash
python3 run_benchmark.py --cpu intel
```

Arm VM:

```bash
python3 run_benchmark.py --cpu arm
```

`--cpu intel` runs the stock profile and `--cpu arm` runs the ARM-optimized
profile. Each also picks up its price from `pricing.json`, so no other flags are
needed. The run stops if the flag does not match the machine it is running on,
so a result cannot be saved under the wrong label.

Then collect both result files on one machine and compare:

```bash
python3 compare_results.py results/
```

## What the Output Means

Each run reports how many iterations it completed and how long each one took:

- **s per iteration:** the headline timing, taken as the median.
- **Iterations/hour:** the same figure as throughput.
- **Cost per 1k iterations:** throughput priced with the VM's hourly rate.
- **Verified:** the digits matched the known expansion of pi.
- **Warnings:** do not quote runs that are unverified, noisy, or too small.

`compare_results.py` prints one row per saved run and stops there. It does not
nominate a winner. See [README-DETAILS.md](README-DETAILS.md) for method,
options, pricing, and troubleshooting.

## License

MIT — see [LICENSE](LICENSE).
