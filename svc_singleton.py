# svc_singleton.py
from connection_service import ConnectionService

service = ConnectionService()      # ONE worker thread, ONE SystemBus
