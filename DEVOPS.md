# Docling AI — DevOps Implementation

## Project description

**Docling AI** is an AI-powered manuscript formatting platform: a researcher uploads a
Word or PDF paper, chooses a journal style (IEEE, APA, …), and the system restructures
it, generates compilable LaTeX, compiles it to PDF, and lets an AI agent edit the result.

The application is split into **three microservices** (React frontend, Node.js auth
service, Python AI service), each packaged as a **hardened Docker image**. A **GitHub
Actions** pipeline tests every service, runs **DevSecOps** gates, builds and scans the
images, deploys them to a **Kubernetes** staging cluster and smoke-tests them, and then
releases the same images to production on **AWS**: all infrastructure there is created
by **Terraform**. The public link is an HTTPS **CloudFront** address.

---

## Architecture

```
                              Internet (HTTPS)
                                    │  https://<id>.cloudfront.net
                                    ▼
 AWS ┌─────────────────────────────────────────────────────────────────────┐
     │  CloudFront (CDN, free HTTPS, security headers)                     │
     │     /*                         /api/auth* /api/projects*            │
     │     │                          /api/v2* /deepscan* /files* /toolkit*│
     │     ▼                                       │  (only CloudFront may │
     │  ┌──────────────┐                           ▼   reach the server)   │
     │  │ S3 (private) │       ┌─────────── EC2 t3.micro ───────────────┐  │
     │  │ React app    │       │  Docker Compose                        │  │
     │  └──────────────┘       │  ┌──────────────┐   ┌───────────────┐  │  │
     │                         │  │ auth-service │   │  ai-service   │──┼──┼─▶ Groq LLM API
     │  SSM Parameter Store ──▶│  │ :8001        │   │  :8000        │  │  │
     │  (encrypted secrets)    │  └──────┬───────┘   └───────────────┘  │  │
     │                         └─────────┼──────────────────────────────┘  │
     └───────────────────────────────────┼─────────────────────────────────┘
                                         ▼
                              MongoDB Atlas (free M0)
```

| Service | Language | Responsibility | Data |
|---|---|---|---|
| **frontend** | React, built to static files | User interface | none |
| **auth-service** | Node.js / Express | Sign-up, login (JWT), projects | MongoDB |
| **ai-service** | Python / FastAPI | Formatting pipeline, LaTeX→PDF, chatbot, DocBot editor | own volume |

The services share no code and no database, talk only over HTTP, and trust each other
through **JWT**: auth-service signs a token at login and ai-service verifies it with the
same key, so the AI service never has to call the auth service.

CloudFront puts the website and both APIs behind **one address**, so the browser makes
same-origin requests (relative URLs like `/api/auth/login`), with no CORS and no API
URLs baked into the build.

---

## How each requirement is met

| Requirement | Where | What |
|---|---|---|
| **Microservices** (3) | `frontend/`, `backend/`, `backend_ai/` | 3 independently built, deployed and scaled services; JWT between them |
| **Docker** (4) | `*/Dockerfile`, `docker-compose.yml`, `deploy/aws/docker-compose.yml` | Multi-stage builds, non-root, healthchecks, `.dockerignore`, Compose for dev **and** production (read-only, capabilities dropped, memory limits) |
| **IaC** (2) | `infra/aws/`, `infra/kind/` | Terraform creates the whole AWS environment (network, firewall, server, IAM, secrets, S3, CloudFront, budget alarm) and the Kubernetes cluster |
| **Kubernetes** (2) | `k8s/` | Deployments, StatefulSet, Services, Ingress, ConfigMap, Secret, PVCs, probes, limits, HPA, NetworkPolicy, rolling updates; deployed in the pipeline's staging stage |
| **CI/CD** (3) | `.github/workflows/ci-cd.yml` | test → security → IaC → build/scan/push → Kubernetes staging → AWS production → smoke test |
| **DevSecOps** (2) | pipeline, `infra/aws/`, manifests | Gitleaks, Trivy (secrets, deps, images, IaC), Hadolint, Bandit, npm audit as blocking gates; keyless deploys (OIDC), no SSH, least-privilege IAM |
| **Cloud provider** (2) | AWS | EC2, S3, CloudFront, Systems Manager, IAM, VPC (and the same app on a local Kubernetes cluster) |
| **Public link** (2) | CloudFront | `https://<id>.cloudfront.net`: HTTPS, fixed for as long as the stack exists |

### Docker
- **Multi-stage frontend**: Node builds the site; the final image holds only nginx and
  the static files. On AWS, the pipeline copies those files out of that same scanned image
  into S3.
- **Non-root everywhere**: numeric `USER` (1000, 10001, 101) so Kubernetes can enforce it.
- **No secrets in images**: per-service build contexts with `.dockerignore`. (The old
  setup built the AI image from the repo root, so `.env` ended up inside it: found and
  fixed in this work.)
- **Reproducible**: `npm ci` from committed lock files; pinned base images.
- **HEALTHCHECK** in every image; `pipefail` so a failed download fails the build.
- **Fast first PDF**: the AI image pre-downloads the LaTeX packages its templates use
  (this takes ~2.5 min at build time; afterwards an IEEE compile takes ~7 s).
- **Production Compose** (`deploy/aws/docker-compose.yml`): all Linux capabilities
  dropped, `no-new-privileges`, read-only auth-service, memory limits, log rotation.

### Infrastructure as Code (Terraform)
`infra/aws/` (production), one file per concern:

| File | Creates |
|---|---|
| `network.tf` | VPC, subnet, internet gateway; security group: **inbound only from CloudFront** (AWS-managed prefix list), outbound only 443 and 27017, **no SSH** |
| `server.tf` | EC2 t3.micro (Amazon Linux 2023), IMDSv2 only, encrypted disk, CPU credits "standard" (cannot run up a bill), Elastic IP, an IAM role that may read only `/docling/*` secrets |
| `user_data.sh` | first boot: Docker, Compose, 2 GB swap |
| `secrets.tf` | SSM Parameter Store SecureStrings (JWT key generated by Terraform) |
| `cdn.tf` | private S3 bucket (CloudFront-only access via OAC), CloudFront with path routing, SPA routing function, security headers |
| `github.tf` | GitHub OIDC identity provider + deploy role (only this repo's `production` environment) |
| `budget.tf` | email alert if spending ever passes $1/month |

`infra/kind/` creates a Kubernetes cluster (kind), Traefik Ingress, metrics-server, the
namespace and secrets. The pipeline uses it for staging; you can also run it on a laptop.
Both stacks have a `.terraform.lock.hcl` pinning provider versions and checksums.

### Kubernetes
- **Self-healing**: liveness/readiness/startup probes on every pod
  (auth-service is *ready* only once MongoDB is connected).
- **Zero-downtime rolling updates** (`maxUnavailable: 0`) for frontend and auth-service.
- **Autoscaling**: HPAs scale frontend and auth-service 2→4 pods at 70% CPU.
- **State**: MongoDB as a StatefulSet; AI data on a PersistentVolumeClaim.
- **Config vs secrets**: ConfigMap for settings, Secret for credentials; each pod gets
  only the secrets it needs.

### CI/CD pipeline
```
 push / PR ─▶ test ──────┐
              security ──┼─▶ build ×3 ──▶ k8s-staging ──▶ deploy-aws ──▶ smoke test
              IaC check ─┘  scan, push     Kubernetes      production     public URL
                            (main only from here)
```
1. **Test**: frontend unit tests + production build, Express syntax check, Python unit tests.
2. **Security**: the DevSecOps gates below.
3. **Validate IaC**: `terraform fmt`/`validate` for both stacks, render the Kubernetes
   manifests, check the production Compose file and the shell scripts.
4. **Build**: one job per service in parallel; each image is scanned by Trivy and pushed to
   GitHub Container Registry, tagged with the commit SHA.
5. **Staging on Kubernetes**: Terraform creates a fresh cluster, the images just built are
   deployed with `kubectl apply -k k8s`, every rollout is awaited, then
   `scripts/smoke-test.sh` runs and the cluster is destroyed.
6. **Production on AWS** (only if staging passed):
   - signs in to AWS **with OIDC**: no AWS keys are stored in GitHub;
   - runs `deploy/aws/deploy.sh` on the server **through AWS Systems Manager** (no SSH):
     it loads the secrets from Parameter Store, pulls this commit's images, restarts
     the containers and waits until both report healthy;
   - copies the website out of the frontend image into S3, then refreshes CloudFront;
   - runs the same smoke test against the public HTTPS link.

### DevSecOps
| Gate | Tool | Blocks on |
|---|---|---|
| Secrets in git history | Gitleaks | any secret |
| Secrets in files | Trivy | any secret |
| Vulnerable dependencies | Trivy (+ `npm audit`) | CRITICAL with a fix available |
| Vulnerable images | Trivy image scan | CRITICAL with a fix available |
| Dockerfile / Kubernetes / Terraform-AWS misconfiguration | Trivy, Hadolint | HIGH / CRITICAL |
| Python code | Bandit | high severity, high confidence |

**AWS security design**: no SSH port and no SSH key (Session Manager instead); the
server is reachable only from CloudFront; IMDSv2 only (blocks SSRF credential theft);
encrypted disk and secrets; least-privilege IAM for the server and for the pipeline;
keyless, short-lived pipeline credentials (OIDC); the registry login on the server uses
the job's token, which expires when the job ends. Trivy findings that only paid services
would fix (WAF, KMS customer keys, flow logs, access-log buckets) are documented
exceptions next to the code (`#trivy:ignore` + reason).

**Runtime hardening**: non-root, read-only filesystems, all capabilities dropped, no
privilege escalation, seccomp (Kubernetes), resource limits, a NetworkPolicy so only
auth-service can reach MongoDB, login rate-limiting (Kubernetes Ingress), security
headers, and `REQUIRE_AUTH=true`, so nobody can use the public site to spend the AI API
key without logging in.

---

## Cost

| What | Price |
|---|---|
| CloudFront (1 TB + 10 M requests/month), CloudFront Functions | always free |
| SSM Parameter Store (standard), Session Manager, Run Command, IAM, OIDC, VPC, security groups | free |
| AWS Budgets (the first 2), S3 (a few MB of website) | free / < $0.01 |
| MongoDB Atlas M0, GitHub Actions + public packages (public repo) | free |
| **EC2 t3.micro + its public IPv4 address + 20 GB disk** (Mumbai) | **≈ $0.45/day (≈ $13.5/month)** unless covered by the free tier |

The server is the only item that can cost money. Whether it does depends on your account:

- **AWS account created before 15 July 2025**: its free tier lasted **12 months from
  sign-up**, so by now it has ended and the server is billed at the rate above.
  To keep this near zero: `terraform apply` shortly before the evaluation and
  `terraform destroy` right after it (a few days ≈ $1–2). The budget alarm emails you
  at $1.
- **New AWS account on the Free plan**: the server is paid from the $100–200 sign-up
  credits, and AWS does not charge a Free-plan account at all. It is free for up to
  6 months. This is the only way to run it **always on at $0**.

Not used, because they cost money: EKS (~$73/month for the control plane alone), NAT
gateways, load balancers, WAF, KMS customer keys.

---

## Deploy to AWS (one-time setup)

**Needs:** an AWS account, [AWS CLI v2](https://aws.amazon.com/cli/), Terraform, and a
free **MongoDB Atlas** M0 cluster (copy its connection string). Run from the `Docling-AI`
folder in PowerShell.

```powershell
# 1. Sign the AWS CLI in (an IAM user with AdministratorAccess, used only for setup)
aws configure                     # region: ap-south-1

# 2. Settings and secrets (the file is gitignored)
copy infra\aws\terraform.tfvars.example infra\aws\terraform.tfvars
notepad infra\aws\terraform.tfvars          # MongoDB URI, Groq key, your email

# 3. Create the AWS environment (~5–10 min; CloudFront is the slow part)
terraform -chdir=infra/aws init
terraform -chdir=infra/aws apply

# 4. Let the server reach MongoDB: Atlas -> Network Access -> Add IP Address
terraform -chdir=infra/aws output server_public_ip

# 5. Tell the pipeline where to deploy
terraform -chdir=infra/aws output github_variables
```

6. On GitHub: **Settings → Secrets and variables → Actions → Variables → New repository
   variable**, once for each of the six values printed in step 5 (`AWS_REGION`,
   `AWS_ROLE_ARN`, `EC2_INSTANCE_ID`, `FRONTEND_BUCKET`, `CLOUDFRONT_DISTRIBUTION_ID`,
   `APP_URL`). With the GitHub CLI, one command does it:
   ```powershell
   (terraform -chdir=infra/aws output -json github_variables | ConvertFrom-Json).PSObject.Properties | ForEach-Object { gh variable set $_.Name --body $_.Value }
   ```
7. Push to `main` (or **Actions → CI/CD → Run workflow**). When it finishes, open the
   `APP_URL`.
8. After the first run, make the three images public: your GitHub profile → **Packages**
   → each `docling-*` package → **Package settings → Change visibility → Public**.
   Public packages are free; private ones get 500 MB of free storage, and the AI image alone is larger.

Optional: add your Groq key as a repository **secret** named `GROQ_API_KEY`, so the
Kubernetes staging stage can use the AI features too. The pipeline works without it.

Keep `infra/aws/terraform.tfstate`: Terraform needs it to change or delete the
environment. It contains secrets, so it is gitignored. Never commit it.

**Remove everything** (stops all charges):
```powershell
terraform -chdir=infra/aws destroy
```

**Look inside the server** (no SSH needed):
```powershell
aws ssm start-session --target <EC2_INSTANCE_ID> --region ap-south-1
sudo docker compose -f /opt/docling/docker-compose.yml ps
```

---

## Run it on your machine

### Docker Compose (development)
```powershell
docker compose up --build        # http://localhost:5173
```

### Kubernetes (the same cluster the pipeline's staging stage uses)

**Needs:** Docker Desktop and about 4 GB of free memory (close Chrome first). Tools:
`terraform`, `kind`, `kubectl`.

```powershell
# 1. Secrets (once)
copy infra\kind\terraform.tfvars.example infra\kind\terraform.tfvars
notepad infra\kind\terraform.tfvars

# 2. Cluster + Ingress + metrics + secrets   (~3 min)
terraform -chdir=infra/kind init
terraform -chdir=infra/kind apply -auto-approve
kind export kubeconfig --name docling

# 3. Build the images and load them into the cluster  (~10 min the first time)
docker build -t docling/frontend:local     frontend
docker build -t docling/auth-service:local backend
docker build -t docling/ai-service:local   backend_ai
kind load docker-image docling/frontend:local docling/auth-service:local docling/ai-service:local --name docling

# 4. Deploy
kubectl apply -k k8s
kubectl -n docling get pods -w               # wait until all are Running (Ctrl+C)
```

Open **http://localhost:8080**. Smoke test:
`& "C:\Program Files\Git\bin\bash.exe" scripts/smoke-test.sh http://localhost:8080`

A temporary public link for the local cluster (Cloudflare Tunnel):
```powershell
kubectl apply -f k8s/public-link/cloudflared.yaml
kubectl -n docling logs deploy/cloudflared | Select-String trycloudflare
```

Remove: `terraform -chdir=infra/kind destroy -auto-approve`

---

## Demo script for the viva

| Show | Where / command | What it proves |
|---|---|---|
| Public link | open `APP_URL` on your phone, sign up, format a paper | cloud deployment, HTTPS |
| The pipeline | GitHub **Actions** → latest run | all stages, gates, staging, production, smoke tests |
| Keyless deploy | the `deploy-aws` job log: "Get temporary AWS credentials (OIDC)" | no AWS keys in GitHub |
| Infrastructure | `terraform -chdir=infra/aws state list` | everything was created by code |
| Server is locked down | EC2 → Security group: inbound only the CloudFront prefix list, port 22 closed | DevSecOps |
| Containers on the server | `aws ssm start-session …` then `docker compose ps` | Docker in production, no SSH |
| Secrets | Systems Manager → Parameter Store → `/docling/*` (SecureString) | not in Git, not in images |
| Security reports | Actions run → `security-report` artifact | Trivy results |
| Kubernetes | the `k8s-staging` job log: pods, services, ingress, HPA, rollouts | Kubernetes deployment |

### Likely questions

**Why microservices here?** The parts have different languages, resource needs and
scaling: the AI service is heavy and does long-running work; auth is tiny and stateless.
Each can be deployed and scaled on its own, and a crash in the AI service does not take
login down.

**Why not EKS (Kubernetes on AWS)?** The EKS control plane alone costs about $73/month,
plus worker nodes, and a 1 GB server cannot run Kubernetes and the app together. So
Kubernetes is used where it is free: as the pipeline's staging stage (a real cluster
created by Terraform for every release), and locally. Production is Docker Compose on
one small server. Moving to EKS would reuse the same images and manifests.

**Why CloudFront and S3?** CloudFront gives a free HTTPS address and a CDN, serves the
React site from S3, and routes the API paths to the server, all on one origin, so no
CORS. The server accepts traffic only from CloudFront, so it is never exposed directly.

**How does the pipeline deploy without passwords or SSH?** GitHub issues the job a
short-lived OpenID Connect token; AWS trusts it only for this repository's `production`
environment and returns temporary credentials for a role that can do exactly four things
(run the deploy command on this server, upload to this bucket, refresh this
distribution, read the result). The command reaches the server through AWS Systems
Manager, whose agent connects outward, so no inbound port is needed.

**Where are the secrets?** In SSM Parameter Store (encrypted), written by Terraform from
a gitignored `terraform.tfvars`; the server's role can read only `/docling/*`, and
deploy.sh writes them to a root-only `.env`. In CI they are GitHub secrets. Gitleaks and
Trivy check every push for leaks.

**How do you roll back?** Images are tagged with the commit SHA. Re-run an older
pipeline run, or on the server run `/opt/docling/deploy.sh <owner> <older-sha>`.

**What does DevSecOps mean here?** Security checks run automatically on every change and
block the pipeline (secrets, vulnerable dependencies and images, misconfigured
Dockerfiles/Kubernetes/Terraform, insecure Python). Add to that the hardened runtime and
the AWS design above.

**What would you change for a real product?** A custom domain with an ACM certificate,
AWS WAF, remote Terraform state (S3 + locking), moving the AI service's files to S3 so
it can scale out, and EKS or ECS once the budget allows.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `deploy-aws` is skipped | the repository variables (setup step 6) are not set |
| `Not authorized to perform sts:AssumeRoleWithWebIdentity` | `github_repository` in `terraform.tfvars` must match the repo exactly (`owner/name`), then `terraform apply` |
| `EntityAlreadyExists` … OpenID Connect provider | the account already has one: set `create_github_oidc_provider = false` |
| `InvalidInstanceId` from `send-command` | the server is still booting: wait 2–3 minutes and re-run the job |
| auth-service never healthy, `/readyz` 503 | add the server IP to Atlas Network Access (setup step 4) |
| `504` from CloudFront | a request took over 60 s (CloudFront's limit); check `docker compose logs` on the server |
| `terraform apply` (kind) fails: port 8080 in use | `terraform -chdir=infra/kind apply -var http_port=8090` |
| Pod `ImagePullBackOff` / `ErrImageNeverPull` (kind) | rerun `kind load docker-image …` |
| Docker Desktop crashes during build | low memory: close apps and retry |
