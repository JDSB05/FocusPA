from .auth_controller import login, register, logout
from .main_controller import (
    dashboard, access_control, compliance,
    receber_log, procurar_logs
)
from .policy_controller import (
    list_policies, policy_new, policy_edit, policy_delete, upload_policy
)
from .anomaly_controller import (
    list_anomalies, get_anomaly, create_anomaly,
    update_anomaly, delete_anomaly
)
from .investigation_controller import (
    list_investigations, start_investigation
)
from .accesslog_controller import list_logs

__all__ = [
    'login', 'register', 'logout',
    'dashboard', 'access_control', 'compliance',
    'receber_log', 'procurar_logs',
    'list_policies', 'policy_new', 'policy_edit', 'policy_delete', 'upload_policy',
    'list_anomalies', 'get_anomaly', 'create_anomaly', 'update_anomaly', 'delete_anomaly',
    'list_investigations', 'start_investigation', 'investigation_detail',
    'list_logs'
]
