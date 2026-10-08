
import sys
import random

def main():
    if len(sys.argv) != 2:
        print("Usage: python samplit-rheagupta14.py <filename>", file=sys.stderr)
        sys.exit(1)
    with open(sys.argv[1]) as f:
        for line in f:
            if random.random() < 0.01:
                print(line, end="")

if __name__ == "__main__":
    main()
