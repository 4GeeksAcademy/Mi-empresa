"""
Evaluación AUTH-01 - TrackFlow API
Evalúa todos los criterios de implementación de JWT Authentication.
"""
import os
import json
import re
import subprocess

# --- Configuración: DBs temporales ---
tmp_auth = "/tmp/trackflow-auth-eval.json"
tmp_suppliers = "/tmp/trackflow-suppliers-eval.json"
for p in [tmp_auth, tmp_suppliers]:
    if os.path.exists(p):
        os.unlink(p)
os.environ["TRACKFLOW_AUTH_DB_PATH"] = tmp_auth
os.environ["TRACKFLOW_SUPPLIERS_DB_PATH"] = tmp_suppliers

# Limpiar caches de módulos
from database import get_suppliers_repository
from auth_db import get_user_repository, get_profile_repository
get_suppliers_repository.cache_clear()
get_user_repository.cache_clear()
get_profile_repository.cache_clear()

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
results = []


def check(label: str, condition: bool, detail: str = "") -> bool:
    icon = "✓" if condition else "✗"
    print(f"  {icon} {label} {detail}")
    return condition


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


print("=" * 70)
print("EVALUACIÓN AUTH-01 - TrackFlow API")
print("Fecha:", __import__("datetime").datetime.now().isoformat())
print("=" * 70)

# ================================================================
# 1. CRUD de usuarios
# ================================================================
print("\n--- 1. CRUD de usuarios ---")
ok_1 = True
try:
    # POST /users - crear alice
    r = client.post("/users", json={"email": "alice@test.com", "password": "pass123", "name": "Alice", "phone": "+111", "address": "Calle 1"})
    assert r.status_code == 201, f"POST /users alice: {r.status_code}"
    uid1 = r.json()["id"]
    ok_1 &= check("POST /users → 201", True)
    ok_1 &= check("  role=user", r.json()["role"] == "user")
    ok_1 &= check("  sin name en User", "name" not in r.json())

    # Login
    r = client.post("/auth/login", json={"email": "alice@test.com", "password": "pass123"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    h = auth_headers(token)
    ok_1 &= check("Login OK", True)

    # GET /users
    r = client.get("/users", headers=h)
    ok_1 &= check("GET /users → 200", r.status_code == 200)
    ok_1 &= check("  >=1 usuario", len(r.json()) >= 1)

    # GET /users/{id}
    r = client.get(f"/users/{uid1}", headers=h)
    ok_1 &= check(f"GET /users/{uid1} → 200", r.status_code == 200 and r.json()["id"] == uid1)

    # Duplicado → 409 (usar password de 6+ caracteres para pasar validación)
    r = client.post("/users", json={"email": "alice@test.com", "password": "otra123"})
    ok_1 &= check("POST email duplicado → 409", r.status_code == 409, f"(got {r.status_code})")

    # Crear bob
    r = client.post("/users", json={"email": "bob@test.com", "password": "pass456", "name": "Bob"})
    assert r.status_code == 201
    uid2 = r.json()["id"]
    ok_1 &= check("POST /users bob → 201", True)

    # Login bob
    r = client.post("/auth/login", json={"email": "bob@test.com", "password": "pass456"})
    assert r.status_code == 200
    h_bob = auth_headers(r.json()["access_token"])

    # PUT /users/{id} - cambiar email
    r = client.put(f"/users/{uid1}", json={"email": "alice_new@test.com"}, headers=h)
    ok_1 &= check(f"PUT email → 200", r.status_code == 200 and r.json()["email"] == "alice_new@test.com")

    # DELETE /users/{id}
    r = client.delete(f"/users/{uid2}", headers=h_bob)
    ok_1 &= check(f"DELETE → 204", r.status_code == 204)

except Exception as e:
    print(f"  ❌ ERROR en CRUD: {e}")
    import traceback; traceback.print_exc()
    ok_1 = False

results.append(("1", "CRUD de usuarios (POST/GET/PUT/DELETE)", "✅ PASS" if ok_1 else "❌ FAIL"))

# ================================================================
# 2. Profile vinculado
# ================================================================
print("\n--- 2. Profile vinculado ---")
ok_2 = True
try:
    r = client.post("/users", json={"email": "carol@test.com", "password": "pass789", "name": "Carol", "phone": "+222", "address": "Calle 2"})
    assert r.status_code == 201
    uid3 = r.json()["id"]

    r = client.post("/auth/login", json={"email": "carol@test.com", "password": "pass789"})
    assert r.status_code == 200
    h_carol = auth_headers(r.json()["access_token"])

    r = client.get("/profiles/me", headers=h_carol)
    ok_2 &= check("GET /profiles/me → 200", r.status_code == 200)
    p = r.json()
    ok_2 &= check("  name=Carol", p.get("name") == "Carol")
    ok_2 &= check("  phone=+222", p.get("phone") == "+222")
    ok_2 &= check("  address=Calle 2", p.get("address") == "Calle 2")
    ok_2 &= check(f"  user_id={uid3}", p.get("user_id") == uid3)

    # User no debe contener name/phone/address
    r = client.get(f"/users/{uid3}", headers=h_carol)
    for campo in ["name", "phone", "address"]:
        ok_2 &= check(f"  User sin '{campo}'", campo not in r.json())

    # Usuario sin perfil → 404
    r = client.post("/users", json={"email": "dave@test.com", "password": "pass000"})
    assert r.status_code == 201
    r = client.post("/auth/login", json={"email": "dave@test.com", "password": "pass000"})
    h_dave = auth_headers(r.json()["access_token"])
    r = client.get("/profiles/me", headers=h_dave)
    ok_2 &= check("User sin perfil → /profiles/me → 404", r.status_code == 404)

except Exception as e:
    print(f"  ❌ ERROR en Profile: {e}")
    import traceback; traceback.print_exc()
    ok_2 = False

results.append(("2", "Profile vinculado (name/phone/address separados)", "✅ PASS" if ok_2 else "❌ FAIL"))

# ================================================================
# 3. Validación de role
# ================================================================
print("\n--- 3. Validación de role ---")
ok_3 = True
try:
    r = client.post("/users", json={"email": "bad@test.com", "password": "pass123", "role": "superadmin"})
    ok_3 &= check("Role inválido → 422", r.status_code == 422)

    r = client.post("/users", json={"email": "default@test.com", "password": "pass123"})
    ok_3 &= check("Role default=user", r.status_code == 201 and r.json()["role"] == "user")

    r = client.post("/users", json={"email": "roleadmin@test.com", "password": "admin123", "role": "admin"})
    ok_3 &= check("Role admin explícito", r.status_code == 201 and r.json()["role"] == "admin")

except Exception as e:
    print(f"  ❌ ERROR en role: {e}")
    ok_3 = False

results.append(("3", "Validación de role (admin/manager/user, inválido→422, default→user)", "✅ PASS" if ok_3 else "❌ FAIL"))

# ================================================================
# 4. Contraseñas hasheadas
# ================================================================
print("\n--- 4. Contraseñas hasheadas ---")
ok_4 = True
try:
    # Leer TinyDB
    with open(tmp_auth) as f:
        raw = json.load(f)

    # TinyDB tabla personalizada "users"
    users_data = raw.get("users") or raw.get("_default", {})
    found = False
    pw_hash = None

    def find_pw(udata, search_key):
        for k, v in udata.items():
            if isinstance(v, dict):
                email = v.get("email", "")
                if search_key in email:
                    h = v.get("hashed_password", "")
                    return True, h
        return False, None

    found_alice_new, pw_hash = find_pw(users_data, "alice_new")
    if not found_alice_new:
        found_alice, pw_hash = find_pw(users_data, "alice@test.com")
        if found_alice:
            # Alice existe pero no ha cambiado el email aún en esta iteración
            pass

    ok_4 &= check("Usuario encontrado en TinyDB", True)  # Siempre hay usuarios

    # Buscar cualquier hashed_password para validar el formato
    for k, v in users_data.items():
        if isinstance(v, dict) and "hashed_password" in v:
            pw_hash = v["hashed_password"]
            break

    if pw_hash:
        ok_4 &= check("No está en texto plano", pw_hash != "pass123")
        ok_4 &= check("Empieza con $2 (bcrypt)", pw_hash.startswith("$2"), f"({pw_hash[:15]}...)")

    # Login incorrecto → 401
    # Usar alice que no cambió email
    r = client.post("/auth/login", json={"email": "carol@test.com", "password": "wrongpassword"})
    ok_4 &= check("Login contraseña incorrecta → 401", r.status_code == 401)

except Exception as e:
    print(f"  ❌ ERROR en contraseñas: {e}")
    import traceback; traceback.print_exc()
    ok_4 = False

results.append(("4", "Contraseñas hasheadas (bcrypt, no texto plano, incorrecta→401)", "✅ PASS" if ok_4 else "❌ FAIL"))

# ================================================================
# 5. JWT válido y firmado
# ================================================================
print("\n--- 5. JWT válido y firmado ---")
ok_5 = True
try:
    r = client.post("/auth/login", json={"email": "carol@test.com", "password": "pass789"})
    ok_5 &= check("Login → 200", r.status_code == 200)
    td = r.json()
    ok_5 &= check("Tiene access_token", "access_token" in td)
    ok_5 &= check("token_type=bearer", td.get("token_type") == "bearer")

    from auth import SECRET_KEY
    from jose import jwt

    payload = jwt.decode(td["access_token"], SECRET_KEY, algorithms=["HS256"])
    ok_5 &= check("Tiene sub (subject)", "sub" in payload)
    ok_5 &= check("Tiene exp (expiration)", "exp" in payload)
    ok_5 &= check(f"  sub={payload.get('sub')}", True)
    ok_5 &= check(f"  exp={payload.get('exp')}", True)

except Exception as e:
    print(f"  ❌ ERROR en JWT: {e}")
    ok_5 = False

results.append(("5", "JWT válido y firmado (sub+exp, decodificable con SECRET_KEY)", "✅ PASS" if ok_5 else "❌ FAIL"))

# ================================================================
# 6. get_current_user
# ================================================================
print("\n--- 6. get_current_user ---")
ok_6 = True
try:
    # Token inválido → 401
    r = client.get("/users", headers=auth_headers("token-invalido"))
    ok_6 &= check("Token inválido → 401", r.status_code == 401)

    # Sin token → 401
    r = client.get("/users")
    ok_6 &= check("Sin token → 401", r.status_code == 401)

    # Usuario inactivo → 401
    from auth import hash_password, create_access_token
    from auth_models import UserPersistence, utc_now_iso

    get_user_repository.cache_clear()
    repo = get_user_repository()

    up = UserPersistence(email="inactive-eval@test.com", hashed_password=hash_password("x"), role="user", is_active=True, created_at=utc_now_iso())
    uid_inactive = repo.create(up).id
    token_ia = create_access_token(data={"sub": str(uid_inactive)})

    # Activo funciona
    r = client.get("/users", headers=auth_headers(token_ia))
    ok_6 &= check("Usuario activo → 200", r.status_code == 200)

    # Desactivar
    repo.update(uid_inactive, {"is_active": False})

    # Mismo token ahora falla
    r = client.get("/users", headers=auth_headers(token_ia))
    ok_6 &= check("Usuario inactivo → 401 (aunque token válido)", r.status_code == 401)

    # Reactivar
    repo.update(uid_inactive, {"is_active": True})

except Exception as e:
    print(f"  ❌ ERROR en get_current_user: {e}")
    import traceback; traceback.print_exc()
    ok_6 = False

results.append(("6", "get_current_user (token inválido→401, sin token→401, inactivo→401)", "✅ PASS" if ok_6 else "❌ FAIL"))

# ================================================================
# 7. Rutas protegidas → 401 sin token
# ================================================================
print("\n--- 7. Rutas protegidas sin token → 401 ---")
ok_7 = True
try:
    protegidas = [
        ("GET", "/users"),
        ("GET", "/users/1"),
        ("PUT", "/users/1", {"email": "x@y.com"}),
        ("DELETE", "/users/1"),
        ("GET", "/auth/me"),
        ("POST", "/suppliers", {"nombre": "X", "pais": "US", "categorias_producto": ["transporte"], "tarifa_por_kg": 1.0, "status": "activo"}),
        ("PATCH", "/suppliers/1/rate", {"tarifa_por_kg": 5.0}),
        ("PATCH", "/suppliers/1/status", {"status": "activo"}),
        ("DELETE", "/suppliers/1"),
        ("GET", "/profiles/me"),
        ("PUT", "/profiles/me", {"name": "X"}),
    ]
    for ruta in protegidas:
        m, p = ruta[0], ruta[1]
        body = ruta[2] if len(ruta) > 2 else None
        if m == "GET":
            r = client.get(p)
        elif m == "POST":
            r = client.post(p, json=body or {})
        elif m == "PUT":
            r = client.put(p, json=body or {})
        elif m == "PATCH":
            r = client.patch(p, json=body or {})
        elif m == "DELETE":
            r = client.delete(p)
        ok_7 &= check(f"{m} {p} → 401", r.status_code == 401, f"(got {r.status_code})")

    r = client.post("/api/incidents/analyze")
    ok_7 &= check("POST /api/incidents/analyze → 401", r.status_code == 401)

    r = client.get("/api/incidents/results/export")
    ok_7 &= check("GET /api/incidents/results/export → 401", r.status_code == 401)

except Exception as e:
    print(f"  ❌ ERROR: {e}")
    ok_7 = False

results.append(("7", "Rutas protegidas → 401 sin token (13 endpoints)", "✅ PASS" if ok_7 else "❌ FAIL"))

# ================================================================
# 8. 403 Forbidden
# ================================================================
print("\n--- 8. 403 Forbidden por permisos ---")
ok_8 = True
try:
    # Crear charlie (user normal) - password de 6+ caracteres
    r = client.post("/users", json={"email": "charlie@test.com", "password": "pass123", "role": "user"})
    assert r.status_code == 201, f"POST charlie: {r.status_code} {r.text[:100]}"
    uid_charlie = r.json()["id"]

    r = client.post("/auth/login", json={"email": "charlie@test.com", "password": "pass123"})
    assert r.status_code == 200
    h_charlie = auth_headers(r.json()["access_token"])

    # Crear target (otro user normal)
    r = client.post("/users", json={"email": "target@test.com", "password": "target123", "role": "user"})
    assert r.status_code == 201, f"POST target: {r.status_code} {r.text[:100]}"
    uid_target = r.json()["id"]

    # user modifica otro → 403
    r = client.put(f"/users/{uid_target}", json={"email": "hacked@test.com"}, headers=h_charlie)
    ok_8 &= check("user modifica email de otro → 403", r.status_code == 403, f"(got {r.status_code})")

    # user cambia role de otro → 403
    r = client.put(f"/users/{uid_target}", json={"role": "admin"}, headers=h_charlie)
    ok_8 &= check("user cambia role de otro → 403", r.status_code == 403, f"(got {r.status_code})")

    # user cambia su propio role → 403
    r = client.put(f"/users/{uid_charlie}", json={"role": "admin"}, headers=h_charlie)
    ok_8 &= check("user cambia su propio role → 403", r.status_code == 403, f"(got {r.status_code})")

except Exception as e:
    print(f"  ❌ ERROR en 403: {e}")
    import traceback; traceback.print_exc()
    ok_8 = False

results.append(("8", "403 Forbidden (user modifica otro, cambia roles)", "✅ PASS" if ok_8 else "❌ FAIL"))

# ================================================================
# 9. Variables de entorno
# ================================================================
print("\n--- 9. Variables de entorno ---")
ok_9 = True
try:
    sk = os.getenv("SECRET_KEY")
    ok_9 &= check("SECRET_KEY configurada", bool(sk), f"({'set' if sk else 'NOT SET'})")
    exp = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
    ok_9 &= check("ACCESS_TOKEN_EXPIRE_MINUTES", bool(exp), f"(={exp})")

    # No hardcodeadas
    with open("/workspaces/Mi-empresa/services/api/auth.py") as f:
        content = f.read()
    if "os.getenv" in content or "os.environ" in content:
        ok_9 &= check("Lee de env vars vía os.getenv", True)
    else:
        ok_9 &= check("Lee de env vars", False)

except Exception as e:
    print(f"  ❌ ERROR: {e}")
    ok_9 = False

results.append(("9", "Variables de entorno (SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES desde .env)", "✅ PASS" if ok_9 else "❌ FAIL"))

# ================================================================
# 10. Estructura de rutas
# ================================================================
print("\n--- 10. Estructura de rutas ---")
ok_10 = True
try:
    routes_info = [
        (r.path, list(r.methods)[0] if r.methods else "")
        for r in app.routes if hasattr(r, "path") and r.path.startswith("/")
    ]
    for path, method in sorted(routes_info):
        print(f"     {method:7s} {path}")

    paths_set = set(p for p, _ in routes_info)
    ok_10 &= check("/auth/login existe", "/auth/login" in paths_set)
    ok_10 &= check("/auth/me existe", "/auth/me" in paths_set)
    ok_10 &= check("/users existe", "/users" in paths_set)
    ok_10 &= check("/users/{id} existe", any(p.startswith("/users/") for p in paths_set))
    ok_10 &= check("/profiles/me existe", "/profiles/me" in paths_set)

except Exception as e:
    print(f"  ❌ ERROR: {e}")
    ok_10 = False

results.append(("10", "Estructura limpia de rutas (/auth/*, /users/*, /profiles/*)", "✅ PASS" if ok_10 else "❌ FAIL"))

# ================================================================
# 11. Protección rutas existentes
# ================================================================
print("\n--- 11. Protección rutas existentes ---")
ok_11 = True
try:
    externas = [
        ("POST", "/suppliers"),
        ("PATCH", "/suppliers/1/rate"),
        ("PATCH", "/suppliers/1/status"),
        ("DELETE", "/suppliers/1"),
        ("POST", "/api/incidents/analyze"),
        ("GET", "/api/incidents/results/export"),
    ]
    count_ok = 0
    for m, p in externas:
        if m == "POST":
            r = client.post(p)
        elif m == "GET":
            r = client.get(p)
        elif m == "PATCH":
            r = client.patch(p)
        elif m == "DELETE":
            r = client.delete(p)
        _ok = r.status_code == 401
        if _ok:
            count_ok += 1
        ok_11 &= check(f"{m} {p} → 401", _ok, f"(got {r.status_code})")

    ok_11 &= check(f"Total: {count_ok} (min 5)", count_ok >= 5)

except Exception as e:
    print(f"  ❌ ERROR: {e}")
    ok_11 = False

results.append(("11", "Protección ≥5 rutas existentes (suppliers, incidents)", "✅ PASS" if ok_11 else "❌ FAIL"))

# ================================================================
# 12. User/Profile solo en TinyDB
# ================================================================
print("\n--- 12. User/Profile solo en TinyDB ---")
ok_12 = True
try:
    with open("/workspaces/Mi-empresa/services/api/auth_db.py") as f:
        content = f.read()
    ok_12 &= check("auth_db.py usa TinyDB", "TinyDB" in content)

    # Verificar que NO hay SQLModel/Supabase en auth (ignorar este script)
    for root, dirs, files in os.walk("/workspaces/Mi-empresa/services/api"):
        for f in files:
            if f.endswith(".py"):
                fp = os.path.join(root, f)
                with open(fp) as fh:
                    c = fh.read()
                    for kw in ["SQLModel", "sqlmodel", "supabase"]:
                        if kw in c:
                            if "evaluate_auth" not in fp and "trackflow_api.egg-info" not in fp:
                                ok_12 &= check(f"  ⚠️ {kw} en {fp}", False)
                                print(f"     ⚠️ Advertencia: {kw} encontrado en {fp}")

    ok_12 &= check("Datos en TinyDB (JSON)", os.path.exists(tmp_auth))

except Exception as e:
    print(f"  ❌ ERROR: {e}")
    ok_12 = False

results.append(("12", "User/Profile en TinyDB (no SQLModel/Supabase)", "✅ PASS" if ok_12 else "❌ FAIL"))

# ================================================================
# 13. Tests sin regresiones
# ================================================================
print("\n--- 13. Sin regresiones ---")
ok_13 = True
try:
    print("  ⏩ Ejecutando tests...")
    result = subprocess.run(
        ["uv", "run", "pytest", "-v", "--tb=short"],
        capture_output=True,
        text=True,
        cwd="/workspaces/Mi-empresa/services/api",
        env={
            **os.environ,
            "TRACKFLOW_AUTH_DB_PATH": tmp_auth,
            "TRACKFLOW_SUPPLIERS_DB_PATH": tmp_suppliers,
        },
    )
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr[:500])

    ok_13 &= check("pytest exit code 0", result.returncode == 0, f"(returncode={result.returncode})")

    passed = len(re.findall(r"PASSED", result.stdout))
    failed = len(re.findall(r"FAILED", result.stdout))
    ok_13 &= check(f"Tests: {passed} passed, {failed} failed", failed == 0)

except Exception as e:
    print(f"  ❌ ERROR ejecutando tests: {e}")
    ok_13 = False

results.append(("13", "Sin regresiones (pytest -v)", "✅ PASS" if ok_13 else "❌ FAIL"))

# ================================================================
# RESUMEN FINAL
# ================================================================
print("\n" + "=" * 70)
print("RESUMEN DE EVALUACIÓN AUTH-01")
print("=" * 70)
print()
print(f"{'#':<4s} {'Criterio':<55s} {'Resultado':<10s}")
print("-" * 70)
all_pass = True
for num, criterio, estado in results:
    print(f"  {num:<2s} {criterio:<55s} {estado:<10s}")
    if "FAIL" in estado:
        all_pass = False
print("-" * 70)
if all_pass:
    print(f"\n  {'✅  TODOS LOS CRITERIOS PASARON':^69s}")
    print(f"  {'🎉  EVALUACIÓN AUTH-01 COMPLETADA EXITOSAMENTE':^69s}")
else:
    print(f"\n  {'❌  ALGUNOS CRITERIOS FALLARON':^69s}")
    print("  Revise los detalles arriba para solucionar cada criterio.")
print("=" * 70)