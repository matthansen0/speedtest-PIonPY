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

Every machine performs the same fixed amount of work. The benchmark runs five
tiers so the sources of any speedup can be separated:

| Tier | Test |
|---|---|
| `baseline` | Naive series, one core |
| `algorithm` | Binary splitting, one core |
| `native` | Binary splitting with GMP, one core |
| `parallel` | Binary splitting, all cores |
| `optimized` | GMP with all cores |

Each result is checked against an independent `mpmath` calculation. Runs use
warm-up and repeated samples, and record median timing, variance, CPU limits,
steal time, interpreter, GMP details, and a result digest.

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
cd ~/speedtest-PIonPY
python3 prepare_benchmark.py
```

Intel VM:

```bash
python3 run_benchmark.py --sku azure_d2s_v5
```

Arm VM:

```bash
python3 run_benchmark.py --sku azure_d2ps_v6
```

## What the Output Means

- **Cost per 1k runs:** lower is better; this is the main comparison.
- **Runs per $:** higher is better.
- **Median seconds:** the sustained timing used for cost.
- **Integrity warnings:** do not rely on failed, noisy, or too-small runs.

The `optimized` tier is the overall result. See [README-DETAILS.md](README-DETAILS.md)
for method, options, pricing, comparisons, and troubleshooting.

## License

MIT — see [LICENSE](LICENSE).
