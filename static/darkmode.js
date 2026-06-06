(function () {
    var CLAVE = 'tema-innova';

    /* Aplica el tema guardado de inmediato para evitar parpadeo */
    var temaGuardado = localStorage.getItem(CLAVE) || 'light';
    document.documentElement.setAttribute('data-theme', temaGuardado);

    document.addEventListener('DOMContentLoaded', function () {

        /* Actualizar texto/ícono de todos los botones al cargar */
        actualizarBotones(temaGuardado);

        /* Asignar evento a todos los botones de modo oscuro */
        document.querySelectorAll(
            '.btn-darkmode, .btn-darkmode-flotante, .btn-darkmode-sidebar'
        ).forEach(function (btn) {
            btn.addEventListener('click', function () {
                var temaActual = document.documentElement.getAttribute('data-theme');
                var nuevoTema = temaActual === 'dark' ? 'light' : 'dark';

                document.documentElement.setAttribute('data-theme', nuevoTema);
                localStorage.setItem(CLAVE, nuevoTema);
                actualizarBotones(nuevoTema);
            });
        });
    });

    /* Actualiza solo el ícono y el label, sin destruir el HTML del botón */
    function actualizarBotones(tema) {
        document.querySelectorAll(
            '.btn-darkmode, .btn-darkmode-flotante, .btn-darkmode-sidebar'
        ).forEach(function (btn) {
            var icono = btn.querySelector('i');
            var label = btn.querySelector('.sidebar-button-label, .nav-label');
            if (tema === 'dark') {
                if (icono) { icono.className = 'bi bi-sun nav-icon'; }
                if (label) { label.textContent = 'Claro'; }
                btn.title = 'Cambiar a modo claro';
            } else {
                if (icono) { icono.className = 'bi bi-moon-stars nav-icon'; }
                if (label) { label.textContent = 'Oscuro'; }
                btn.title = 'Cambiar a modo oscuro';
            }
        });
    }
})();