-- A lancer UNE fois, avec un compte proprietaire de la table `users` (ou superutilisateur).
-- Rattache les comptes Keycloak aux utilisateurs existants (tâches et groupes conservés).
ALTER TABLE users ADD COLUMN IF NOT EXISTS keycloak_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS users_keycloak_id_uniq ON users (keycloak_id);
