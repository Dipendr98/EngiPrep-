import sqlite3

import config


def run(code: str, stdin: str = '', timeout: int = config.CODE_TIMEOUT) -> dict:
    """Execute SQL against an in-memory SQLite database using Python's sqlite3 module."""
    output_lines = []
    errors = []

    try:
        conn = sqlite3.connect(':memory:')
        cursor = conn.cursor()

        # Split on semicolons and execute each non-empty statement
        statements = [s.strip() for s in code.split(';') if s.strip()]
        for stmt in statements:
            try:
                cursor.execute(stmt)
                if cursor.description:
                    cols = [d[0] for d in cursor.description]
                    output_lines.append(' | '.join(cols))
                    output_lines.append('-' * (sum(len(c) for c in cols) + 3 * (len(cols) - 1)))
                    for row in cursor.fetchall():
                        output_lines.append(' | '.join(str(v) if v is not None else 'NULL' for v in row))
            except sqlite3.Error as exc:
                errors.append(f'SQL Error: {exc}')

        conn.commit()
        conn.close()
    except Exception as exc:
        return {
            'status': 'runtime_error',
            'stdout': '\n'.join(output_lines),
            'stderr': str(exc),
            'exit_code': 1,
        }

    if errors:
        return {
            'status': 'runtime_error',
            'stdout': '\n'.join(output_lines),
            'stderr': '\n'.join(errors),
            'exit_code': 1,
        }

    return {
        'status': 'success',
        'stdout': '\n'.join(output_lines),
        'stderr': '',
        'exit_code': 0,
    }
