
define docker_rebuild
	docker compose -p $(1) -f docker/$(1)/docker-compose.yml down && \
	docker compose -p $(1) -f docker/$(1)/docker-compose.yml rm -f && \
	docker compose -p $(1) -f docker/$(1)/docker-compose.yml pull && \
	docker compose -p $(1) -f docker/$(1)/docker-compose.yml build --no-cache && \
	docker compose -p $(1) -f docker/$(1)/docker-compose.yml up -d
endef

define docker_remove
	docker compose -p $(1) -f docker/$(1)/docker-compose.yml down && \
	docker compose -p $(1) -f docker/$(1)/docker-compose.yml rm -f
endef

init:
	@echo "Initializing project..."
	docker network create --driver bridge reverse-proxy

# Portainer
portainer:
	docker volume create portainer_data
	$(call docker_rebuild,"portainer")

# NGINX Proxy Manager
nginxpm:
	docker volume create nginxpm_data
	docker volume create nginxpm_letsencrypt
	$(call docker_rebuild,"nginxpm")

# NTFY SERVER
ntfy:
	docker volume create ntfy_data
	$(call docker_rebuild,"ntfy")

# NOTIFICATIONS SERVICES
notifications:
	docker volume create notifications_ntfy-data
	docker volume create notifications_apprise-config
	docker volume create notifications_apprise-plugin
	docker volume create notifications_apprise-attach
	$(call docker_rebuild,"notifications")