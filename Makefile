# Function: Docker Rebuild
# [execute: down, remove, pull, build, up]
# $(call docker_rebuild,"stack_name")
define docker_rebuild
	docker compose -p $(1) -f docker/$(1)/docker-compose.yml down && \
	docker compose -p $(1) -f docker/$(1)/docker-compose.yml rm -f && \
	docker compose -p $(1) -f docker/$(1)/docker-compose.yml pull && \
	docker compose -p $(1) -f docker/$(1)/docker-compose.yml build --no-cache && \
	docker compose -p $(1) -f docker/$(1)/docker-compose.yml up -d
endef
# Function: Docker Remove
# [execute: down, remove]
# $(call docker_remove,"stack_name")
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
# docker volume create ntfy_data
	$(call docker_rebuild,"ntfy")