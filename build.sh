#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate

# Create superuser if it doesn't exist (requires DJANGO_SUPERUSER_PASSWORD env var)
python manage.py ensure_superuser

# Run seed scripts based on environment variables
if [ "$DJANGO_RUN_SEED" = "1" ]; then
    echo "🌱 Running seed_demo_data (services, products, users)..."
    python manage.py seed_demo_data

    echo "🌱 Running seed_staff_availability..."
    python manage.py seed_staff_availability

    echo "🌱 Running seed_dosha_questions..."
    python manage.py seed_dosha_questions

    echo "🌱 Running seed_blog..."
    python manage.py seed_blog

    echo "✅ All seeds completed successfully!"
fi
