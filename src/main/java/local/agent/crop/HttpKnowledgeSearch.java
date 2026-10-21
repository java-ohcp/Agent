package local.agent.crop;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.Objects;
import static local.agent.crop.Contracts.*;

/** Client only: no HTTP server, crawler, vector store or backend implementation. */
public final class HttpKnowledgeSearch implements KnowledgeSearch {
    private final URI endpoint;
    private final String bearerToken;
    private final HttpClient http;
    private final ObjectMapper json = new ObjectMapper();

    public HttpKnowledgeSearch(URI endpoint, String bearerToken) {
        this.endpoint = Objects.requireNonNull(endpoint);
        if (!List.of("http", "https").contains(endpoint.getScheme()) || endpoint.getHost() == null
                || endpoint.getUserInfo() != null) {
            throw new IllegalArgumentException("Knowledge endpoint must be an HTTP(S) URL without credentials");
        }
        this.bearerToken = bearerToken;
        this.http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER).build();
    }

    @Override
    public List<Evidence> search(SearchQuery query) throws Exception {
        var request = HttpRequest.newBuilder(endpoint).timeout(Duration.ofSeconds(15))
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json.writeValueAsString(query)));
        if (bearerToken != null && !bearerToken.isBlank()) {
            request.header("Authorization", "Bearer " + bearerToken);
        }
        var response = http.send(request.build(), HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() != 200) {
            throw new IllegalStateException("Knowledge service returned HTTP " + response.statusCode());
        }
        if (response.body().length() > 1_000_000) {
            throw new IllegalStateException("Knowledge response is too large");
        }
        var body = json.readValue(response.body(), SearchResponse.class);
        if (body == null || body.matches() == null) throw new IllegalStateException("Missing matches");
        return List.copyOf(body.matches());
    }
}
