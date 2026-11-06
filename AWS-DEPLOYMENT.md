# EC2 HTTP demonstration

GitHub Actions builds both linux/amd64 images and publishes `latest` and commit
SHA tags to GHCR on pushes to main (or manual execution on main). EC2 only pulls
images. No EC2 credentials or deployment secrets are needed in Actions.

This deployment serves the UI and API schema. Authentication, assessments, AI
tutoring and RAG require supporting services and are not functional in this demo.
The deep `/api/v1/health/` check also requires those services; do not use it as a
container readiness check for this deployment.

## First deployment

1. Wait for **Publish Docker images** to succeed in GitHub Actions. Make both GHCR
   packages public, or log in on EC2 with a token authorized for `read:packages`
   using `docker login ghcr.io --username YOUR_GITHUB_USERNAME --password-stdin`.
   Supply the token through stdin; never store it in this repository.
2. Copy only `docker-compose.aws.yml` into your EC2 deployment directory. Keep
   the existing EC2 `.env` in that directory unchanged. If none exists, create it
   privately (`touch .env && chmod 600 .env`) and populate any needed configuration.
   Never copy the repository's historical `.env` onto EC2.
3. Allow inbound TCP 80 in the EC2 security group; keep TCP 8000 closed. Restrict
   SSH to your administration IP. Confirm sufficient disk with `df -h` and
   `docker system df` before pulling; the available 3.7 GB must hold image layers
   and extraction space. No local builds or supporting service containers run.
4. From that directory, run:

   ```sh
   docker compose -f docker-compose.aws.yml config --quiet
   docker compose -f docker-compose.aws.yml pull
   docker compose -f docker-compose.aws.yml up -d --no-build
   docker compose -f docker-compose.aws.yml ps
   curl -f http://127.0.0.1/
   curl -f http://127.0.0.1/api/v1/health/live
   curl -f http://127.0.0.1/api/v1/openapi.json
   docker stats --no-stream learnmate_api learnmate_frontend
   ```

   Review failures with `docker compose -f docker-compose.aws.yml logs --tail=100`.
   Test the UI at `http://EC2_PUBLIC_IP/`. No GitHub workflow deploys to EC2.

## Updates and limitations

Repeat `pull` then `up -d --no-build` after a successful publish. Review unused
images with `docker system df`; remove obsolete images only after deciding which
rollback images to retain. Container logs are rotated to bound disk use.

The API has one worker capped at 384 MB; Nginx is capped at 128 MB. Monitor actual
memory and disk use on the t3.micro. These limits do not guarantee that future
application changes will fit.

Compose explicitly selects the existing development authentication mode for this
HTTP-only demonstration. It does not modify `.env` or relax application validation.
Do not use real accounts or sensitive data. A full deployment needs supporting
services, HTTPS, a private signing key, secure cookies and production mode.

## Repository security finding

The root `.env` was tracked before this deployment change. It is now untracked
and remains ignored; the local file is retained. Historical commits still contain
it. Rotate any real credentials that have appeared there. Git history is not
rewritten by this change. Build contexts exclude environment files and local
dependencies so they cannot enter the published images.
