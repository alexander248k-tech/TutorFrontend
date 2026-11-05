import { CommonModule } from '@angular/common';
import { ChangeDetectorRef, Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { IonContent } from '@ionic/angular';
import { TimeoutError, finalize, timeout } from 'rxjs';

import { ApiService } from '../../services/api';

@Component({
  selector: 'app-login',
  templateUrl: './login.page.html',
  styleUrls: ['./login.page.scss'],
  standalone: true,
  imports: [CommonModule, FormsModule, IonContent]
})
export class LoginPage {
  private readonly router = inject(Router);
  private readonly apiService = inject(ApiService);
  private readonly cdr = inject(ChangeDetectorRef);

  correo = '';
  password = '';
  cargando = false;
  mensajeError = '';

  mostrarPassword = false;
  mensajeEstado = '';

  private readonly TIMEOUT_MS = 30000;

  togglePassword(): void {
    this.mostrarPassword = !this.mostrarPassword;
  }

  mostrarAlertaRecuperacion(event: Event): void {
    event.preventDefault();
    this.mensajeEstado = ' Para recuperar tu contraseña, contacta al administrador del sistema estelar.';
  }

 
  private refrescar(): void {
    this.cdr.detectChanges();
  }

  onLogin(): void {
    if (this.cargando) return;

    if (!this.correo.trim() || !this.password) {
      this.mensajeError = 'Por favor completa todos los campos.';
      this.mensajeEstado = ' Campos incompletos.';
      return;
    }

    this.cargando = true;
    this.mensajeError = '';
    this.mensajeEstado = 'Autenticando en el sistema...';

    const correo = this.correo.trim();

    this.apiService
      .facerLogin(correo, this.password)
      .pipe(timeout(this.TIMEOUT_MS))
      .subscribe({
        next: (res: any) => {
          console.log('Respuesta de login:', res);

          sessionStorage.setItem('correo', correo);
          if (res?.usuario || res?.nombre) {
            sessionStorage.setItem('usuario', res.usuario || res.nombre);
          }

          this.pedirInfoUsuario(correo);
        },
        error: (err: any) => {
          console.error('Error en el login:', err);
          this.cargando = false;

          if (err instanceof TimeoutError) {
            this.mensajeError = 'El servidor tardó demasiado en responder. Intenta de nuevo.';
            this.mensajeEstado = ' Tiempo de espera agotado.';
          } else if (err?.status === 0) {
            this.mensajeError = 'No se pudo conectar con el servidor (red o CORS).';
            this.mensajeEstado = ' Sin conexión.';
          } else {
            this.mensajeError = 'Credenciales incorrectas o error de conexión.';
            this.mensajeEstado = ' Error de autenticación.';
          }
          this.refrescar();
        }
      });
  }

  
  private pedirInfoUsuario(correo: string): void {
    const payloadPedirInfo = {
      accion: 'Configuracion',
      editar: 'PedirInfo',
      payload: {
        correo
      }
    };

    this.apiService
      .enviarConfiguracion(payloadPedirInfo)
      .pipe(
        timeout(this.TIMEOUT_MS),
        finalize(() => {
          this.cargando = false;
          this.refrescar();
        })
      )
      .subscribe({
        next: (infoRes: any) => {
          console.log('Información del usuario obtenida:', infoRes);
          const nivel = String(infoRes?.nivelIngles || infoRes?.nivel || infoRes?.NivelIngels || 'A1');
          sessionStorage.setItem('nivelIngles', nivel);
          sessionStorage.setItem('nivelActual', nivel);

          this.mensajeEstado = '✨ ¡Acceso concedido!';
          void this.router.navigate(['/menu']);
        },
        error: (err: any) => {
          console.warn('No se pudo obtener el nivel, se usa A1:', err);
          sessionStorage.setItem('nivelIngles', 'A1');
          sessionStorage.setItem('nivelActual', 'A1');
          void this.router.navigate(['/menu']);
        }
      });
  }

  irRegistro(): void {
    void this.router.navigate(['/register']);
  }
}