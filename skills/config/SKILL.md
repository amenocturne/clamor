---
name: config
description: Configuration and infrastructure patterns. Use when working with Ansible, Docker, YAML configs, server setup, deployment, or infrastructure code. Triggers on "ansible", "docker", "deployment", "server config", "infrastructure", "devops", "compose".
author: amenocturne
---

# Configuration & Infrastructure

Ansible, Docker, and YAML-heavy projects.

## Stack

| Purpose | Tool |
|---------|------|
| Provisioning | Ansible |
| Containers | Docker / Docker Compose |
| Secrets | .env files (gitignored) |
| Validation | Python scripts with uv |

## Commands

```bash
just setup       # Copy template files, initialize
just validate    # Check syntax and prerequisites
just test-local  # Test in local Docker environment
just dry-run     # Plan without applying
just deploy      # Apply configuration
just ping        # Test connectivity
just logs <svc>  # View service logs
```

## Ansible Structure

```
ansible/
├── playbooks/
│   └── site.yml              # Main orchestration
├── roles/
│   └── <role>/
│       ├── tasks/main.yml    # Role tasks
│       ├── handlers/main.yml # Handlers
│       ├── templates/        # Jinja2 templates
│       ├── files/            # Static files
│       └── defaults/main.yml # Default variables
├── inventories/
│   ├── hosts.yml.template    # Template for users
│   └── production.yml        # Actual inventory (gitignored)
└── group_vars/
    └── all.yml               # Global variables
```

## Ansible Patterns

### Variables

```yaml
# group_vars/all.yml
app_name: myapp
app_port: 8080
app_env: production

# Use in templates
server {
    listen {{ app_port }};
    server_name {{ app_name }}.example.com;
}
```

### Tasks

```yaml
- name: Create app directory
  file:
    path: "{{ app_dir }}"
    state: directory
    owner: "{{ app_user }}"
    mode: "0755"

- name: Copy configuration
  template:
    src: config.yml.j2
    dest: "{{ app_dir }}/config.yml"
  notify: Restart app
```

### Handlers

```yaml
- name: Restart app
  systemd:
    name: "{{ app_name }}"
    state: restarted
    daemon_reload: true
```

### Conditionals and Loops

```yaml
- name: Install packages
  apt:
    name: "{{ item }}"
    state: present
  loop:
    - nginx
    - certbot

- name: Configure firewall
  ufw:
    rule: allow
    port: "{{ item }}"
  loop: "{{ open_ports }}"
  when: configure_firewall | bool
```

## Docker Compose

```yaml
services:
  app:
    image: myapp:latest
    container_name: myapp
    restart: unless-stopped
    ports:
      - "127.0.0.1:${APP_PORT}:8080"
    environment:
      - DATABASE_URL=${DATABASE_URL}
    volumes:
      - app_data:/data
    networks:
      - internal

  db:
    image: postgres:15
    container_name: myapp_db
    restart: unless-stopped
    environment:
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - db_data:/var/lib/postgresql/data
    networks:
      - internal

volumes:
  app_data:
  db_data:

networks:
  internal:
```

### Environment Files

```bash
# .env.template (committed)
APP_PORT=8080
DATABASE_URL=postgres://user:PASSWORD@db:5432/myapp
DB_PASSWORD=changeme

# .env (gitignored, actual values)
APP_PORT=8080
DATABASE_URL=postgres://myapp:secretpass@db:5432/myapp
DB_PASSWORD=secretpass
```

## Testing Workflow

1. **Validate** - `just validate` checks syntax, required files
2. **Local test** - `just test-local` deploys to Docker container
3. **Dry run** - `just dry-run` shows what would change
4. **Deploy** - `just deploy` applies to production

## Security Practices

- Never commit secrets - use `.env` files (gitignored)
- Template files end in `.template` and are committed
- Use Ansible Vault for sensitive playbook variables
- SSH keys never in repo
- Firewall rules explicit, deny by default

## File Organization

```
project/
├── ansible/
├── docker/
│   ├── compose/
│   │   ├── app.yml
│   │   └── monitoring.yml
│   └── test-environment/     # Local testing
├── scripts/
│   ├── validate.py
│   ├── deploy.py
│   └── health_check.py
├── .env.template
├── justfile
└── CLAUDE.md
```

## Anti-patterns

- Hardcoded IPs or passwords
- Ansible tasks without `name:`
- Docker containers as root when avoidable
- Committing `.env` files
- Skipping validation before deploy
- Manual changes on servers (drift)
