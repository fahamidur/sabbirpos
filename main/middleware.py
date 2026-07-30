from django.shortcuts import redirect


class AdminLoginRequiredMiddleware:
    """
    Require admin session for internal routes.
    Public ecommerce and auth endpoints remain accessible.
    """

    PUBLIC_EXACT_PATHS = {
        "/",
        "/logout/",
        "/homepage",
        "/cart/",
        "/checkout/",
        "/place-order/",
        "/salesman/login/",
        "/salesman/logout/",
        "/auth/request-reset-code/",
        "/auth/reset-credentials/",
        "/admin/",
    }

    PUBLIC_PREFIXES = (
        "/product/",
        "/api/",
        "/static/",
        "/media/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        # Keep public paths accessible
        if path in self.PUBLIC_EXACT_PATHS or any(path.startswith(p) for p in self.PUBLIC_PREFIXES):
            return self.get_response(request)

        # Allow admin if logged in
        if request.session.get("is_logged_in"):
            return self.get_response(request)

        # Allow salesman POS flow separately
        if path.startswith("/salesman/") and request.session.get("salesman_id"):
            return self.get_response(request)

        return redirect("login")
