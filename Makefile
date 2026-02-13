IMAGE_NAME = simulator-building
NETWORK ?= bacnet_net

.PHONY: building stop

building:
	@echo "Starting building simulation..."
	@docker build -q -t bacnet-building-simulator -f simulators/building/Dockerfile simulators/building > /dev/null
	$(call ensure-network)
	@# Remove existing building simulators
	@docker ps -a --filter "name=simulator-building-" --format "{{.ID}}" \
		| xargs -r docker rm -f > /dev/null 2>&1 || true
	@# AHU
	@docker run -d --name simulator-building-ahu --network $(NETWORK) --restart unless-stopped \
		bacnet-building-simulator --name Building-AHU-1 --instance 400001 --equipment ahu > /dev/null
	@echo "  Started AHU-1 (ID: 400001)"
	@# VAVs
	@for i in 0 1 2 3 4 5; do \
		FLOOR=$$(( ($$i / 2) + 1 )); \
		if [ $$(($$i % 2)) -eq 0 ]; then ZONE="North"; else ZONE="South"; fi; \
		INSTANCE=$$((400010 + $$i)); \
		docker run -d \
			--name "simulator-building-vav$$i" \
			--network $(NETWORK) \
			--restart unless-stopped \
			bacnet-building-simulator \
			--name "Floor$${FLOOR}-VAV-$${ZONE}" --instance "$$INSTANCE" --equipment "vav$$i" > /dev/null; \
		echo "  Started Floor$${FLOOR}-VAV-$${ZONE} (ID: $$INSTANCE)"; \
	done
	@# Chiller
	@docker run -d --name simulator-building-chiller --network $(NETWORK) --restart unless-stopped \
		bacnet-building-simulator --name Building-Chiller-1 --instance 400020 --equipment chiller > /dev/null
	@echo "  Started Chiller-1 (ID: 400020)"
	@# Meter
	@docker run -d --name simulator-building-meter --network $(NETWORK) --restart unless-stopped \
		bacnet-building-simulator --name Building-Main-Meter --instance 400030 --equipment meter > /dev/null
	@echo "  Started Main-Meter (ID: 400030)"
	@echo "Done. 9 BACnet devices running on '$(NETWORK)'."

stop:
	@echo "Stopping all containers..."
	@docker ps -a --filter "name=simulator-" --filter "name=obs-demo-" --format "{{.ID}}" \
		| xargs -r docker rm -f > /dev/null 2>&1 || true
	@echo "Done."
