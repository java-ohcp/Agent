package local.agent.crop;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.DeserializationFeature;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.Objects;
import java.nio.ByteBuffer;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Flow;
import static local.agent.crop.Contracts.*;

/** Client only: no HTTP server, crawler, vector store or backend implementation. */
public final class HttpKnowledgeSearch implements KnowledgeSearch {
    private final URI endpoint;
    private final String bearerToken;
    private final HttpClient http;
    private final ObjectMapper json = new ObjectMapper().enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

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
        var response = http.send(request.build(), ignored -> new BoundedBodySubscriber());
        if (response.statusCode() != 200) {
            throw new IllegalStateException("Knowledge service returned HTTP " + response.statusCode());
        }
        var root = json.readTree(response.body());
        if (root != null && root.has("code")) {
            if (!root.path("code").isIntegralNumber() || root.path("code").asInt(-1) != 0) {
                throw new IllegalStateException("Knowledge service returned an application error");
            }
            root = root.path("data");
        }
        var body = root == null ? null : json.treeToValue(root, SearchResponse.class);
        if (body == null || body.matches() == null) throw new IllegalStateException("Missing matches");
        return List.copyOf(body.matches());
    }

    /** Cancel before buffering more than 1 MiB; preserve the HttpClient request deadline. */
    private static final class BoundedBodySubscriber implements HttpResponse.BodySubscriber<String> {
        private final HttpResponse.BodySubscriber<String> delegate = HttpResponse.BodySubscribers.ofString(java.nio.charset.StandardCharsets.UTF_8);
        private Flow.Subscription subscription;
        private long bytes;
        private boolean stopped;
        @Override public CompletionStage<String> getBody() { return delegate.getBody(); }
        @Override public void onSubscribe(Flow.Subscription value) { subscription = value; delegate.onSubscribe(value); }
        @Override public void onNext(List<ByteBuffer> buffers) {
            if (stopped) return;
            bytes += buffers.stream().mapToLong(ByteBuffer::remaining).sum();
            if (bytes > 1_048_576) {
                stopped = true;
                subscription.cancel();
                delegate.onError(new IOException("Knowledge response exceeds 1 MiB"));
            } else delegate.onNext(buffers);
        }
        @Override public void onError(Throwable error) { if (!stopped) { stopped = true; delegate.onError(error); } }
        @Override public void onComplete() { if (!stopped) { stopped = true; delegate.onComplete(); } }
    }
}
