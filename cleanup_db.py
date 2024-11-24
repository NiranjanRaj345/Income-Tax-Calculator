import sqlite3

# Connect to the database
conn = sqlite3.connect('data/tax_calculator.db')
cursor = conn.cursor()

# Drop the temporary table if it exists
cursor.execute('DROP TABLE IF EXISTS _alembic_tmp_admin')

# Commit the changes and close the connection
conn.commit()
conn.close()
