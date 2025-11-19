# Alembic Migration Guide

This guide explains how to use Alembic migrations to manage your database schema changes safely and prevent data loss.

## Prerequisites

1. Make sure Alembic is installed:
   ```bash
   pip install -r requirements.txt
   ```

2. Ensure your `.env` file has the `DATABASE_URL` environment variable set.

## Initial Setup

The Alembic configuration has been set up for you. The structure is:
- `alembic.ini` - Main configuration file
- `alembic/env.py` - Environment configuration (configured for async SQLAlchemy)
- `alembic/versions/` - Directory containing migration files

## Common Migration Commands

### 1. Create a New Migration

When you modify your models in `app/models.py`, create a new migration:

```bash
cd backend
alembic revision --autogenerate -m "Description of changes"
```

This will:
- Compare your current models with the database state
- Generate a new migration file in `alembic/versions/`
- **IMPORTANT**: Review the generated migration file before applying it!

### 2. Review the Generated Migration

Always review the generated migration file to ensure:
- It includes all the changes you expect
- It doesn't include unintended changes
- Data migration steps are included if needed (e.g., for column renames, data transformations)

### 3. Apply Migrations

To apply pending migrations to your database:

```bash
cd backend
alembic upgrade head
```

This will apply all migrations up to the latest version.

### 4. Apply a Specific Migration

To upgrade to a specific revision:

```bash
alembic upgrade <revision_id>
```

### 5. Rollback a Migration

To rollback the last migration:

```bash
alembic downgrade -1
```

To rollback to a specific revision:

```bash
alembic downgrade <revision_id>
```

### 6. Check Current Database Version

To see what migration version your database is currently at:

```bash
alembic current
```

### 7. View Migration History

To see all migrations and their status:

```bash
alembic history
```

### 8. Show Pending Migrations

To see what migrations haven't been applied yet:

```bash
alembic heads
```

## Best Practices

### 1. Always Review Generated Migrations

Alembic's autogenerate is smart but not perfect. Always review the generated migration file:

```python
# Example: If you rename a column, Alembic might generate:
# op.drop_column('table', 'old_name')
# op.add_column('table', sa.Column('new_name', ...))
# 
# This will cause DATA LOSS! Instead, you should manually edit it to:
# op.alter_column('table', 'old_name', new_column_name='new_name')
```

### 2. Test Migrations on Development First

Always test migrations on a development database before applying to production:

```bash
# 1. Create a backup of your database
# 2. Apply the migration
alembic upgrade head
# 3. Test your application
# 4. If something goes wrong, restore from backup
```

### 3. Handle Data Migrations Manually

For complex changes that require data transformation, edit the migration file:

```python
def upgrade() -> None:
    # Add new column
    op.add_column('customers', sa.Column('full_name', sa.String(200)))
    
    # Migrate data from old columns to new column
    op.execute("""
        UPDATE customers 
        SET full_name = CONCAT(first_name, ' ', last_name)
    """)
    
    # Drop old columns (if needed)
    # op.drop_column('customers', 'first_name')
    # op.drop_column('customers', 'last_name')
```

### 4. Never Modify Applied Migrations

Once a migration has been applied to production, **never modify it**. Instead, create a new migration to fix any issues.

### 5. Use Descriptive Migration Messages

Always use clear, descriptive messages:

```bash
# Good
alembic revision --autogenerate -m "Add email field to customers table"

# Bad
alembic revision --autogenerate -m "update"
```

## Workflow Example

Here's a typical workflow when making schema changes:

1. **Modify your models** in `app/models.py`:
   ```python
   class Customer(Base):
       # ... existing fields ...
       email = Column(String(120), nullable=True)  # New field
   ```

2. **Generate migration**:
   ```bash
   alembic revision --autogenerate -m "Add email field to customers"
   ```

3. **Review the generated file** in `alembic/versions/`:
   ```python
   def upgrade() -> None:
       op.add_column('customers', sa.Column('email', sa.String(length=120), nullable=True))
   ```

4. **Test the migration** on development:
   ```bash
   alembic upgrade head
   ```

5. **Apply to production** (after testing):
   ```bash
   alembic upgrade head
   ```

## Important Notes

- **Backup your database** before running migrations in production
- The initial migration (`001_initial_migration.py`) represents your current schema. If your database already has tables, you may need to mark this migration as already applied:
  ```bash
  alembic stamp head  # Marks current database state as up-to-date
  ```
- If you're starting fresh, you can apply the initial migration:
  ```bash
  alembic upgrade head
  ```

## Troubleshooting

### Migration conflicts
If you have migration conflicts, you can:
1. Check the current state: `alembic current`
2. View history: `alembic history`
3. Resolve conflicts manually or create a merge migration

### Database out of sync
If your database is out of sync with migrations:
```bash
# See what's different
alembic check

# If needed, create a migration to sync
alembic revision --autogenerate -m "Sync database state"
```

## Removing the Startup Table Creation

Once you're using Alembic, you should remove the automatic table creation from `app/main.py`:

```python
# Remove or comment out this line:
# await conn.run_sync(Base.metadata.create_all)
```

Instead, rely on Alembic migrations to manage your schema.

