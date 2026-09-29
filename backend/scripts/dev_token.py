"""Print an access token for a local test account, for trying the API in Swagger.

Creates the account (email pre-confirmed) on first use. Development only.

Usage (from backend/, venv active):
    python -m scripts.dev_token --email you+dev@example.com --password "a-long-dev-password"

Then open http://127.0.0.1:8000/docs, click "Authorize" and paste the token.
Tokens expire after about an hour; run the command again for a new one.
"""

import argparse
import sys

from scripts.dev_users import ensure_confirmed_user, sign_in


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True, help="at least 6 characters")
    args = parser.parse_args()

    user_id = ensure_confirmed_user(args.email, args.password)
    token = sign_in(args.email, args.password)
    print(f"\nUser id: {user_id}\n\nAccess token (paste into Swagger > Authorize):\n\n{token}\n", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
