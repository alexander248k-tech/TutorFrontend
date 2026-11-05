import type { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    redirectTo: 'login',
    pathMatch: 'full',
  },
  {
    path: 'login',
    loadComponent: () => import('./pages/login/login.page').then(m => m.LoginPage)
  },
  {
    path: 'register',
    loadComponent: () => import('./pages/register/register.page').then(m => m.RegisterPage)
  },
  {
    path: 'menu',
    loadComponent: () => import('./pages/menu/menu.page').then(m => m.MenuPage)
  },
  {
    path: 'niveles',
    loadComponent: () => import('./pages/niveles/niveles.page').then(m => m.NivelesPage)
  },
  {
    path: 'chat', // <--- ¡Aquí está la pieza que faltaba!
    loadComponent: () => import('./pages/chat/chat.page').then(m => m.ChatPage)
  },
  {
    path: 'tabs',
    loadChildren: () => import('./tabs/tabs.routes').then(m => m.routes)
  },
  {
    path: 'aprender', // <--- ¡Módulo de aprendizaje y práctica integrado!
    loadComponent: () => import('./pages/aprender/aprender.page').then(m => m.AprenderPage)
  },
];