"use client";
import { MapContainer, TileLayer, Marker, Popup, Polyline } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { classifyHop, Hop } from "../utils/tracerouteClassification";

// Optional: fix missing marker icons in Leaflet
const iconUrl = 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png';
const iconShadowUrl = 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png';

const DefaultIcon = L.icon({
  iconUrl,
  shadowUrl: iconShadowUrl,
});
L.Marker.prototype.options.icon = DefaultIcon;

export default function TraceMap({ hops, target }: { hops: Hop[]; target: string }) {
  const validHops = hops.filter(h => h.geo && h.geo.lat != null && h.geo.lon != null);
  const positions = validHops.map(h => [h.geo.lat!, h.geo.lon!] as [number, number]);

  if (positions.length === 0) return null;

  const center = positions[0];

  return (
    <MapContainer
      center={center}
      zoom={2}
      scrollWheelZoom={true}
      style={{ height: "500px", width: "100%", marginTop: "2rem" }}
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution="&copy; OpenStreetMap contributors"
      />

      {validHops.map((hop, idx) => {
        const lat = hop.geo?.lat;
        const lon = hop.geo?.lon;
        if (lat == null || lon == null) return null;
        const classification = classifyHop(hop, target);
        return (
          <Marker key={idx} position={[lat, lon]} icon={DefaultIcon}>
            <Popup>
              <strong>Hop {hop.hop}</strong><br />
              {hop.hostname} ({hop.ip})<br />
             {classification.ownership && (
                  <>
                    📍 {classification.ownership.label}
                    {classification.ownership.city ? ` (${classification.ownership.city})` : ""}
                    <br />
                 </>
              )}     
         
              {hop.latency}<br />
              {classification.explanation || "Hop details available."}
            </Popup>
          </Marker>
        );
      })}

      <Polyline positions={positions} color="blue" />
    </MapContainer>
  );
}
