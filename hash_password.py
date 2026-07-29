#!/usr/bin/env python3
"""Generate a bcrypt hash for an admin/app password.

Usage:
    python scripts/hash_password.py
Then paste the printed hash into your .env as ADMIN_PASSWORD_HASH=...
The plaintext password is never stored anywhere.
"""

import getpass

import bcrypt


def main():
    pw = getpass.getpass("Enter password to hash: ")
    pw2 = getpass.getpass("Confirm password: ")
    if pw != pw2:
        raise SystemExit("Passwords do not match.")
    if len(pw) < 10:
        print("WARNING: use at least 10 characters for a production password.")
    h = bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
    print("\nAdd this to your .env (do NOT commit it):\n")
    print(f"ADMIN_PASSWORD_HASH={h}")


if __name__ == "__main__":
    main()
