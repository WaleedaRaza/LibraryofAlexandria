"""Promote one exact LibXNDR account to reviewer/admin status."""

from __future__ import annotations

import argparse

from app.db.database import get_db, get_supabase, init_db, is_sqlite_mode


def main() -> None:
    parser = argparse.ArgumentParser(description="Grant reviewer access to one exact account email.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--confirm-admin", action="store_true")
    args = parser.parse_args()
    email = args.email.strip().casefold()
    if not args.confirm_admin:
        raise SystemExit("Refusing to change a role without --confirm-admin")
    init_db()
    if is_sqlite_mode():
        db = get_db()
        rows = db.execute("SELECT id,email,role FROM users WHERE lower(email)=?", (email,)).fetchall()
        if len(rows) != 1:
            raise SystemExit(f"Expected exactly one account for {email}; found {len(rows)}")
        db.execute("UPDATE users SET role='admin' WHERE id=?", (rows[0]["id"],))
        db.commit()
    else:
        rows = get_supabase().table("users").select("id,email,role").ilike("email", email).execute().data or []
        exact = [row for row in rows if row["email"].casefold() == email]
        if len(exact) != 1:
            raise SystemExit(f"Expected exactly one account for {email}; found {len(exact)}")
        get_supabase().table("users").update({"role": "admin"}).eq("id", exact[0]["id"]).execute()
    print(f"Reviewer access granted to {email}")


if __name__ == "__main__":
    main()
