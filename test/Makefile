base:
	$(OSBUILD) --input $(BASE_INPUT) --output $(BASE_OUTPUT) 1-create-base.json

web:
	$(OSBUILD) --input $(BASE_OUTPUT) --output $(WEB_OUTPUT) 2-configure-web-server.json

qcow2:
	$(OSBUILD) --input $(WEB_OUTPUT) --output $(QCOW2_OUTPUT) 3-compose-qcow2.json