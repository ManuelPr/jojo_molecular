from casmi26.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["mini-train", *__import__("sys").argv[1:]]))

