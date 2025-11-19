import streamlit as st

def check_password():
    """Checks the password against secrets."""
    # Secrets are nested under [auth] in secrets.toml
    auth = st.secrets.get("auth", {})
    login = auth.get("login", None)
    password = auth.get("password", None)

    if st.session_state.get("username") == login and st.session_state.get("password") == password:
        st.session_state["authenticated"] = True
        # Clear sensitive data from session state
        if "password" in st.session_state:
            del st.session_state["password"]
        if "username" in st.session_state:
            del st.session_state["username"]
    else:
        st.error("Неверный логин или пароль")

def require_auth():
    """Enforces authentication. Stops execution if not authenticated."""
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.title("Вход в систему")
        st.text_input("Логин", key="username")
        st.text_input("Пароль", type="password", key="password")
        st.button("Войти", on_click=check_password)
        st.stop()
