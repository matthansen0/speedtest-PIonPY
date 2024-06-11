# Uses the ``mpmath`` library, which has built-in methods to calculate Pi to a high precision.

import mpmath
import time  # Ensure this import is at the top of your file

mpmath.mp.dps = 10000  # set number of decimal places

# Calculate Pi using the Chudnovsky algorithm
def calculate_pi():
    C = 426880 * mpmath.sqrt(10005)
    K = 6
    M = 1
    X = 1
    L = 13591409
    S = L
    total_iterations = 10000  # Total number of iterations
    ten_percent = total_iterations / 10  # Calculate what 10% of the iterations is
    milestone_start_time = time.time()  # Record the start time for the first milestone

    for i in range(1, total_iterations + 1):
        M = (K**3 - 16*K) * M // i**3
        L += 545140134
        X *= -262537412640768000
        S += mpmath.mpf(M * L) / X
        K += 12

        # Check if the current iteration has reached the next 10% milestone
        if i % ten_percent == 0:
            current_time = time.time()
            milestone_duration = current_time - milestone_start_time
            print(f"Progress: {int(i/total_iterations*100)}% completed in {milestone_duration} seconds")
            milestone_start_time = current_time  # Reset the milestone start time for the next 10%

    pi = C / S
    return pi

# Set the precision and calculate Pi
pi = calculate_pi()

# Convert Pi to a string
pi_str = str(pi)

# Record the end time
end_time = time.time()

# Calculate the duration
duration = end_time - start_time

# Get the last 50 digits
last_50_digits = pi_str[-50:]

print("The last 50 digits of Pi are:", last_50_digits)
print(f"The Pi calculation took {duration} seconds.")