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

    /* Actualiza el texto e ícono de todos los botones según el tema */
    function actualizarBotones(tema) {
        document.querySelectorAll(
            '.btn-darkmode, .btn-darkmode-flotante, .btn-darkmode-sidebar'
        ).forEach(function (btn) {
            if (tema === 'dark') {
                btn.innerHTML = '&#9728;&#65039; Claro';
                btn.title = 'Cambiar a modo claro';
            } else {
                btn.innerHTML = '&#127769; Oscuro';
                btn.title = 'Cambiar a modo oscuro';
            }
        });
    }
})();
