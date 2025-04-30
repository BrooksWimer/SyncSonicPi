# svc_singleton.py
from syncsonic_ble.flow.connection_service import ConnectionService

service = ConnectionService()      # ONE worker thread, ONE SystemBus
