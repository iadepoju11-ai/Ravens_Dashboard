FROM python:3.12-slim

WORKDIR /app

# `apt-get upgrade` (CHECKLIST.md Phase 7D) -- a real `trivy` scan of this
# image found CRITICAL, fixed CVEs in the base image's own OS packages
# (perl-base, unrelated to anything this app imports) that `python:3.12-slim`
# hadn't been rebuilt with yet; upgrading at build time picks up whatever
# patched packages the Debian security repos already have, rather than
# waiting on a fresh base-image tag.
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV FLASK_ENV=production
EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app.main:app"]
