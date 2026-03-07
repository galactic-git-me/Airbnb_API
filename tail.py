import time
import random
from rich.console import Console
from rich.text import Text
from rich.panel import Panel

def tail_log_file(file_path):
    console = Console()
    colors = ["red", "green", "yellow", "blue", "magenta", "cyan", "white"]

    with open(file_path, 'r') as file:
        # Read and print all lines in the file
        lines = file.readlines()
        for line in lines:
            color = random.choice(colors)
            text = Text(line.strip(), style=color)
            console.print(Panel(text, style=color))

        # Start tailing the file for new lines
        while True:
            line = file.readline()
            if line:
                color = random.choice(colors)
                text = Text(line.strip(), style=color)
                console.print(Panel(text, style=color))  # Print new lines as they are added
            else:
                time.sleep(0.1)  # No new line, wait a bit before retrying

if __name__ == "__main__":
    log_file_path = input("Please enter the location of the log file: ")
    try:
        tail_log_file(log_file_path)
    except FileNotFoundError:
        print(f"Error: The file at {log_file_path} was not found.")
    except KeyboardInterrupt:
        print("Exiting log tailing.")
