import {useEffect, useMemo, useState} from "react";
import {searchExternalStations, searchManagedStations} from "./api/stations";
import {useAuth} from "./auth/AuthContext";
import {AuthDialog, type AuthMode} from "./components/AuthDialog";
import {StationCard} from "./components/StationCard";
import {StationMap} from "./components/StationMap";
import type {Coordinates, StationMarker} from "./types/station";

const INDORE: Coordinates = {latitude: 22.7196, longitude: 75.8577};
type SourceFilter = "all" | "bookable" | "external";

export function App() {
  const {status: authStatus, user, logout} = useAuth();
  const [authDialogMode, setAuthDialogMode] = useState<AuthMode | null>(null);
  const [center, setCenter] = useState<Coordinates>(INDORE);
  const [radiusKm, setRadiusKm] = useState(25);
  const [stations, setStations] = useState<StationMarker[]>([]);
  const [filter, setFilter] = useState<SourceFilter>("all");
  const [selectedStationId, setSelectedStationId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("Searching near Indore…");

  const visibleStations = useMemo(() => {
    if (filter === "bookable") {
      return stations.filter((station) => station.bookable);
    }
    if (filter === "external") {
      return stations.filter((station) => station.source === "open_charge_map");
    }
    return stations;
  }, [filter, stations]);

  useEffect(() => {
    const controller = new AbortController();
    void loadStations(center, radiusKm, controller.signal);
    return () => controller.abort();
  }, []);

  async function loadStations(
    searchCenter: Coordinates,
    searchRadius: number,
    signal?: AbortSignal,
  ) {
    setLoading(true);
    setMessage("Searching for charging stations…");

    const search = {...searchCenter, radiusKm: searchRadius};
    const [managedResult, externalResult] = await Promise.allSettled([
      searchManagedStations(search, signal),
      searchExternalStations(search, signal),
    ]);

    if (signal?.aborted) return;

    const managed = managedResult.status === "fulfilled" ? managedResult.value : [];
    const external = externalResult.status === "fulfilled" ? externalResult.value : [];
    const combined = [...managed, ...external].sort(
      (left, right) => (left.distanceKm ?? Infinity) - (right.distanceKm ?? Infinity),
    );

    setStations(combined);
    setSelectedStationId(combined[0]?.id ?? null);
    setLoading(false);

    if (managedResult.status === "rejected" && externalResult.status === "rejected") {
      setMessage("The station services are unavailable. Confirm that the Flask API is running.");
    } else if (externalResult.status === "rejected") {
      setMessage(`Showing ${managed.length} ChargeMate stations; open-data locations are unavailable.`);
    } else {
      setMessage(`Found ${combined.length} stations within ${searchRadius} km.`);
    }
  }

  function useMyLocation() {
    if (!navigator.geolocation) {
      setMessage("Location access is not supported by this browser.");
      return;
    }

    setMessage("Waiting for your location permission…");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const nextCenter = {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        };
        setCenter(nextCenter);
        void loadStations(nextCenter, radiusKm);
      },
      () => setMessage("Location permission was not granted. You can continue with Indore."),
      {enableHighAccuracy: true, timeout: 10000},
    );
  }

  return (
    <main>
      <header className="site-header">
        <a className="brand" href="#top" aria-label="ChargeMate home">
          <span className="brand-mark" aria-hidden="true">C</span>
          <span>ChargeMate</span>
        </a>
        <nav aria-label="Primary navigation">
          <a href="#stations">Stations</a>
          <a href="#how-it-works">How it works</a>
          {authStatus === "loading" ? (
            <span className="auth-loading">Checking session...</span>
          ) : user ? (
            <div className="account-actions">
              <a className="user-pill" href="#account" title={user.email}>
                <span>{user.full_name.charAt(0).toUpperCase()}</span>
                {user.full_name}
              </a>
              <button
                className="login-button"
                type="button"
                onClick={() => {
                  void logout().catch(() => {
                    setMessage(
                      "The local session was cleared, but the server could not be reached.",
                    );
                  });
                }}
              >
                Log out
              </button>
            </div>
          ) : (
            <div className="account-actions">
              <button
                className="login-button"
                type="button"
                onClick={() => setAuthDialogMode("login")}
              >
                Log in
              </button>
              <button
                className="signup-button"
                type="button"
                onClick={() => setAuthDialogMode("register")}
              >
                Create account
              </button>
            </div>
          )}
        </nav>
      </header>

      <section className="hero" id="top">
        <div className="hero-copy">
          <p className="eyebrow">EV charging, made certain</p>
          <h1>Find your next charge.<br /><span>Know it’s available.</span></h1>
          <p className="hero-description">
            Discover nearby chargers, compare connectors, and reserve a verified
            ChargeMate slot before you arrive.
          </p>
          <div className="hero-actions">
            <a className="primary-action" href="#stations">Explore stations</a>
            <button className="secondary-action" type="button" onClick={useMyLocation}>
              Use my location
            </button>
          </div>
        </div>
        <div className="hero-stat" aria-label="Platform promise">
          <span className="pulse" />
          <p>Live availability</p>
          <strong>Book before<br />you drive.</strong>
        </div>
      </section>

      {user && (
        <section className="account-summary" id="account">
          <div>
            <p className="eyebrow">Signed in securely</p>
            <h2>{user.full_name}</h2>
            <p>{user.email} · @{user.username}</p>
          </div>
          <dl>
            <div><dt>Account role</dt><dd>{user.role.replace("_", " ")}</dd></div>
            <div><dt>Member since</dt><dd>{new Date(user.created_at).toLocaleDateString()}</dd></div>
            <div><dt>Phone</dt><dd>{user.phone ?? "Not provided"}</dd></div>
          </dl>
        </section>
      )}

      <section className="explorer" id="stations">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Station explorer</p>
            <h2>Charging around you</h2>
          </div>
          <div className="search-controls">
            <label>
              Search radius
              <select
                value={radiusKm}
                onChange={(event) => setRadiusKm(Number(event.target.value))}
              >
                <option value={10}>10 km</option>
                <option value={25}>25 km</option>
                <option value={50}>50 km</option>
                <option value={100}>100 km</option>
              </select>
            </label>
            <button
              type="button"
              onClick={() => void loadStations(center, radiusKm)}
              disabled={loading}
            >
              {loading ? "Searching…" : "Search this area"}
            </button>
          </div>
        </div>

        <div className="filter-row" aria-label="Station source filters">
          {(["all", "bookable", "external"] as SourceFilter[]).map((option) => (
            <button
              key={option}
              type="button"
              className={filter === option ? "filter-active" : ""}
              onClick={() => setFilter(option)}
            >
              {option === "all" ? "All stations" : option === "bookable" ? "Bookable" : "Open data"}
            </button>
          ))}
          <span role="status">{message}</span>
        </div>

        <div className="explorer-grid">
          <div className="station-list" aria-label="Charging station results">
            {visibleStations.length > 0 ? (
              visibleStations.map((station) => (
                <StationCard
                  key={station.id}
                  station={station}
                  selected={selectedStationId === station.id}
                  onSelect={() => setSelectedStationId(station.id)}
                />
              ))
            ) : (
              <div className="empty-state">
                <strong>No matching stations</strong>
                <span>Try a larger radius or another station filter.</span>
              </div>
            )}
          </div>
          <div className="map-shell">
            <StationMap
              center={center}
              stations={visibleStations}
              selectedStationId={selectedStationId}
              onSelectStation={setSelectedStationId}
            />
            <div className="map-legend">
              <span><i className="legend-dot legend-dot--bookable" /> Bookable</span>
              <span><i className="legend-dot legend-dot--external" /> Open data</span>
            </div>
          </div>
        </div>
      </section>

      <section className="steps" id="how-it-works">
        <p className="eyebrow">Built around certainty</p>
        <h2>Three steps to a reliable charge</h2>
        <div className="step-grid">
          <article><span>01</span><h3>Discover</h3><p>Search nearby stations using real geospatial distance.</p></article>
          <article><span>02</span><h3>Reserve</h3><p>Hold an available connector without overlapping another driver.</p></article>
          <article><span>03</span><h3>Charge</h3><p>Pay securely and keep a metered record of every session.</p></article>
        </div>
      </section>

      <AuthDialog
        open={authDialogMode !== null}
        initialMode={authDialogMode ?? "login"}
        onClose={() => setAuthDialogMode(null)}
      />
    </main>
  );
}
