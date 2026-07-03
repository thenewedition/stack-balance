#!/usr/bin/env python3
"""Start Stack Balance: python run.py [--host 127.0.0.1] [--port 8321]"""

import argparse

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Stack Balance — self-hosted budgeting")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8321)
    parser.add_argument("--reload", action="store_true", help="dev auto-reload")
    args = parser.parse_args()
    uvicorn.run("stackbalance.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
