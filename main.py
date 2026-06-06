from webApp import create_app

# this is the videoManager entry point.
def main() -> int:
    return_code = 0

    app = create_app()

    app.run(
        host="0.0.0.0",
        port=8080,
        debug=False
    )

    return return_code


if __name__ == "__main__":
    exit(
        main()
    )