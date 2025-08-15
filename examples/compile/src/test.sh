#! /bin/bash
if [[ "${CI:-}" == "" ]]; then
  # shellcheck disable=SC1091
  . global_variables.sh
fi
# Make the artifact from the build stage executable
chmod +x "${EXECUTABLE_NAME}"
# Create a dummy test file with sample input data
# In a real scenario, this might be a more complex test script or set of files.
echo "1000.00" > test_input.dat
echo "Running test with input from test_input.dat..."
# Execute the program and pipe the test data into it.
# Then, use 'grep' to check if the output contains the expected result.
# This is a simple example; a real test would be more robust.
# Let's assume for a $1000 gross pay, the expected tax is $150.00.
./"$EXECUTABLE_NAME" < test_input.dat | grep "Calculated Tax: 150.00"
echo "Test passed: The calculated tax is correct."