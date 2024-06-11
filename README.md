# SpeedTest-PiOnPy

Welcome to SpeedTest-PiOnPy, a comprehensive Python project dedicated to exploring and benchmarking the performance of calculating Pi across various CPU architectures. This project aims to provide insights into how different computational strategies and optimizations can impact the efficiency and speed of Pi calculations on diverse hardware setups.

## Project Overview

SpeedTest-PiOnPy leverages advanced mathematical algorithms and Python's multiprocessing capabilities to divide and conquer the task of calculating Pi. By optimizing for different CPU architectures, this project sheds light on the fascinating world of computational mathematics and its practical implications in hardware performance.

## Features

- **Multi-Architecture Support**: Tailored optimizations for a variety of CPU architectures to ensure maximum performance.
- **High Precision Calculations**: Utilize Python's `mpmath` library for high-precision Pi calculations.
- **Benchmarking Tools**: Includes tools for benchmarking and comparing performance across different systems.
- **Progress Reporting**: Real-time progress reporting for long-running calculations, providing insights into the calculation process.

## Getting Started

To get started with SpeedTest-PiOnPy, follow these simple steps:

1. **Clone the Repository**

   ``bash
   git clone https://github.com/yourusername/speedtest-PIonPY.git
   cd speedtest-PIonPY``

2. **Install Dependencies**

Ensure you have Python 3.x installed on your system. Then, install the required Python libraries:

For Arm and AMD:

``sudo apt install python3-pip``

``pip install -r requirements.txt``

For Intel:

``sudo apt install python3-pip pypy``

``pypy3 -m pip install -r requirements.txt``

3. **Run the Benchmark**

Execute the main script to start the benchmark:

For Arm and AMD: 

``python3 armPi.py`` or ``python3 amdPi.py`` 

For Intel:

``pypy3 intelPi.py``

## Contributing

I welcome contributions from the community! Whether it's adding new optimizations, improving the documentation, or reporting bugs, your contributions are greatly appreciated. Please refer to the CONTRIBUTING.md file for more information on how to contribute.

## Acknowledgments

This project owes its existence to the invaluable assistance provided by ChatGPT and GitHub Copilot. Their contributions have been instrumental in shaping the project's direction and implementation. In the spirit of good humor, any issues encountered will be cheerfully blamed on them. :smile:

## License

This project is licensed under the MIT License - see the LICENSE file for details.