# SpeedTest: Pi-on-Py

<p align="center">
  <img src="media/pionpy.png" alt="Pi on Py" title="Pi on Py" width="400"/>
</p>

Welcome to the Pi-on-Py Speedtest, a Python project dedicated to exploring and benchmarking the performance of calculating Pi across various CPU architectures. This project aims to provide insights into how different computational strategies and optimizations can impact the efficiency and speed of Pi calculations on diverse hardware setups.

## Project Overview

The Pi-on-Py Speedtest leverages advanced mathematical algorithms and Python's multiprocessing capabilities to divide and conquer the task of calculating Pi. By optimizing for different CPU architectures, this project sheds light on the fascinating world of computational mathematics and its practical implications in hardware performance.

## Features

- **Multi-Architecture Support**: Tailored optimizations for a variety of CPU architectures to ensure maximum performance.
- **High Precision Calculations**: Utilize Python's `mpmath` library for high-precision Pi calculations.
- **Benchmarking Tools**: Includes tools for benchmarking and comparing performance across different systems.
- **Progress Reporting**: Real-time progress reporting for long-running calculations, providing insights into the calculation process.

## Understanding CPU Architecture Differences

The SpeedTest-PiOnPy project is designed to run on multiple CPU architectures, including Arm, AMD, and Intel. Each of these architectures has unique characteristics that can impact the performance of computational tasks. Here's a brief overview:

- **Arm**: Known for its power efficiency, Arm processors are widely used in mobile devices and increasingly in servers and desktops. The project's optimizations for Arm leverage multiprocessing to distribute the Pi calculation workload across all available CPU cores, maximizing performance per watt and making it ideal for energy-conscious environments.

- **AMD**: AMD CPUs, particularly those with the EPYC architecture, offer a high number of cores and threads, making them well-suited for parallel processing tasks. The optimizations for AMD aim to leverage this multi-threading capability to speed up the Pi calculation process.

- **Intel**: Intel processors are renowned for their high single-core performance, which is crucial for tasks that cannot be easily parallelized. The project includes specific optimizations for Intel CPUs to take advantage of their architecture, such as using `pypy` for faster Python execution. `pypy` is a Python interpreter with a JIT (Just-In-Time) compilation feature that accelerates the execution of Python code, making it a perfect match for Intel's high-performance cores.

By tailoring the optimizations to each CPU architecture, Pi-on-Py ensures that users can achieve the best possible performance regardless of their hardware setup. This approach allows for a more accurate comparison of hardware capabilities across different systems and architectures.

## Getting Started

To get started, follow these simple steps:

1.) **Clone the Repository**

``git clone https://github.com/matthansen0/speedtest-PIonPY``

``cd speedtest-PIonPY``

2.) **Install Dependencies**

Ensure you have Python 3.x installed on your system. Then, install the required Python libraries:

**Recommended: Use a Python virtual environment (works for AMD, ARM, and Intel):**

```bash
sudo apt install python3-pip python3-venv -y
```

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

3.) **Run the Benchmark**

Single command (auto-detects architecture, uses all cores):

```bash
python3 run_benchmark.py
```

Output shows detected vendor, elapsed time (color-coded), last 50 digits (approximate), and writes a JSON results file (e.g. `results_*.json`).

Automatic optimizations now included:
* Warm-up pass (1% of iterations) for cache/JIT stabilization
* Core affinity pinning (best-effort) to reduce migration
* ARM big.LITTLE frequency weighting (allocates more work to faster cores)
* Intel auto re-exec under PyPy if available for JIT speedups
* JSON result artifact for later comparison
* Always-on per-segment (10%) progress reporting

Progress checkpoints (10% per worker segment) are displayed by default. Iteration count is fixed internally (10,000) for consistent cross-architecture comparison; a warm-up (unreported) precedes the main run.

![Intel Example](media/intel_example.png "Intel Example")

## Notes on Accuracy & Future Enhancements

The current single-script benchmark uses an approximate segmented parallel method to stress CPUs uniformly. It is suitable for relative throughput comparisons (the goal of this project) but is not a mathematically strict parallelization of the Chudnovsky series. Future improvements may include:

- Exact per-term or binary-splitting implementation (mathematically rigorous)
- JSON output mode for automated comparisons
- Optional correctness validation against known π prefixes
- Thermal / frequency sampling during runs

## Contributing

I welcome contributions from the community! Whether it's adding new optimizations, improving the documentation, or reporting bugs, your contributions are greatly appreciated. Please refer to the CONTRIBUTING.md file for more information on how to contribute.

### To-Do List

Here are the next steps for the SpeedTest-PiOnPy project to enhance its functionality and user experience:

- [ ] **Optimize Algorithm Efficiency**: Further refine the mathematical algorithms to improve calculation speed without sacrificing accuracy.
- [ ] **Enhance User Interface**: Develop a more interactive and user-friendly interface for the benchmarking tools.

## Acknowledgments

This project owes its existence to the invaluable assistance provided by ChatGPT and GitHub Copilot. Their contributions have been instrumental in shaping the project's direction and implementation. In the spirit of good humor, any issues encountered will be cheerfully blamed on them. :smile:

## License

This project is licensed under the MIT License - see the LICENSE file for details.
