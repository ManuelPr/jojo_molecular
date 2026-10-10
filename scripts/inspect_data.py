from casmi26.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["inspect-data", *__import__("sys").argv[1:]]))

