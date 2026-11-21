# STRIPEFORGE shortcuts (see scripts/). Example: make setup && make start
.PHONY: setup setup-science start start-dev stop status check check-full migrate-plan
setup:          ; scripts/setup.sh
setup-science:  ; scripts/setup.sh --science
start:          ; scripts/start.sh
start-dev:      ; scripts/start.sh --dev
stop:           ; scripts/stop.sh
status:         ; scripts/status.sh
check:          ; scripts/check.sh
check-full:     ; scripts/check.sh --full
migrate-plan:   ; scripts/migrate.sh
