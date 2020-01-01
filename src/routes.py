from src.views.user import routes as user_routes
from src.views.organization import routes as organization_routes
from src.views.equipment import routes as equipment_routes
from src.views.maintenance import routes as order_routes


def setup_routes(app):
    app.router.add_routes(user_routes)
    app.router.add_routes(organization_routes)
    app.router.add_routes(equipment_routes)
    app.router.add_routes(order_routes)
