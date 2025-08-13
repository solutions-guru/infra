#!/bin/bash

# Use -e to exit immediately if a command fails.
set -e

# 1. Go to the project directory. This is essential so your script
#    can find relative files and the .env file.
#    Replace with the ABSOLUTE path to your project.
cd /home/user/my_project/

# 2. Activate the virtual environment.
#    This ensures the correct Python interpreter and packages are used.
source .venv/bin/activate

# 3. Load the environment variables from the .env file.
#    This command exports all variables from the .env file into the shell session.
#    It's safe and works on most systems.
export $(grep -v '^#' .env | xargs)

# 4. Run your Python script.
#    Now that the environment is fully configured, you can run the script.
#    It's good practice to use the absolute path to python here as well.
/home/user/my_project/.venv/bin/python main.py

echo "Script finished at $(date)"
