#include <boost/python.hpp>
#include <bitcoin/bitcoin.hpp>

//#define SUPRESS_OUTPUT

namespace python = boost::python;
namespace ph = std::placeholders;

class ensure_gil
{
public:
    ensure_gil()
    {
        state_ = PyGILState_Ensure();
    }
    ~ensure_gil()
    {
        PyGILState_Release(state_);
    }
private:
    PyGILState_STATE state_;
};

class pyfunction
{
public:
    pyfunction(python::object callable)
      : callable_(callable)
    {
    }

    template <typename... Args>
    void operator()(Args... params)
    {
        ensure_gil eg;
        try
        {
            callable_(std::forward<Args>(params)...);
        }
        catch (const python::error_already_set&)
        {
            PyErr_Print();
            python::handle_exception();
        }
    }
private:
    python::object callable_;
};

class tx_sentinel
{
public:
    tx_sentinel();

    void start(bool display_output,
        size_t threads, size_t number_hosts,
        python::object handle_newtx, python::object handle_start);
    void stop();

    size_t total_connections() const;

private:
    void connection_started(
        const std::error_code& ec, bc::network::channel_ptr node);
    void inventory_received(const std::error_code& ec,
        const bc::inventory_type& packet, bc::network::channel_ptr node);

    std::ofstream outfile_, errfile_;

    bc::threadpool pool_;
    bc::network::hosts hosts_;
    bc::network::handshake handshake_;
    bc::network::network network_;
    bc::network::protocol p2p_;
    python::object handle_newtx_;
};

void log_nothing(
    bc::log_level level, const std::string& domain, const std::string& body)
{
}
void log_to_file(std::ofstream& file,
    bc::log_level level, const std::string& domain, const std::string& body)
{
    if (body.empty())
        return;
    file << level_repr(level);
    if (!domain.empty())
        file << " [" << domain << "]";
    file << ": " << body << std::endl;
}

tx_sentinel::tx_sentinel()
  : hosts_(pool_), handshake_(pool_), network_(pool_),
    p2p_(pool_, hosts_, handshake_, network_)
{
}

void p2p_started(bc::network::protocol& p2p, const std::error_code& ec,
    python::object handle_start);

// Start the p2p network. Is called repeatedly until connected.
void start_p2p(bc::network::protocol& p2p, python::object handle_start)
{
    p2p.start(std::bind(p2p_started, std::ref(p2p), ph::_1, handle_start));
}

// If there's an error then attempt to reconnect until successful.
void p2p_started(bc::network::protocol& p2p, const std::error_code& ec,
    python::object handle_start)
{
    if (ec)
    {
        bc::log_warning() << "Restarting connection...";
        start_p2p(p2p, handle_start);
        return;
    }
    pyfunction pyh(handle_start);
    // Success. Call finish callback to signal success.
    pyh();
}

void tx_sentinel::start(bool display_output,
    size_t threads, size_t number_hosts,
    python::object handle_newtx, python::object handle_start)
{
    if (display_output)
    {
        bc::log_debug().set_output_function(log_nothing);
        bc::log_info().set_output_function(log_nothing);
        bc::log_warning().set_output_function(log_nothing);
        bc::log_error().set_output_function(log_nothing);
        bc::log_fatal().set_output_function(log_nothing);
    }
    else
    {
        outfile_.open("debug.txrad.log");
        errfile_.open("error.txrad.log");
        bc::log_debug().set_output_function(std::bind(
            log_to_file, std::ref(outfile_), ph::_1, ph::_2, ph::_3));
        bc::log_info().set_output_function(std::bind(
            log_to_file, std::ref(outfile_), ph::_1, ph::_2, ph::_3));
        bc::log_warning().set_output_function(std::bind(
            log_to_file, std::ref(errfile_), ph::_1, ph::_2, ph::_3));
        bc::log_error().set_output_function(std::bind(
            log_to_file, std::ref(errfile_), ph::_1, ph::_2, ph::_3));
        bc::log_fatal().set_output_function(std::bind(
            log_to_file, std::ref(errfile_), ph::_1, ph::_2, ph::_3));
    }

    pool_.spawn(threads);

    handle_newtx_ = handle_newtx;
    // Set connection counts.
    p2p_.set_max_outbound(number_hosts);
    // Notify us of new connections so we can subscribe to 'inv' packets.
    p2p_.subscribe_channel(
        std::bind(&tx_sentinel::connection_started, this, ph::_1, ph::_2));
    // Start connecting to p2p networks for broadcasting and monitor txs.
    start_p2p(p2p_, handle_start);
}
void tx_sentinel::stop()
{
    pool_.stop();
    pool_.join();
}

void tx_sentinel::connection_started(
    const std::error_code& ec, bc::network::channel_ptr node)
{
    if (ec)
    {
        bc::log_warning() << "Couldn't start connection: " << ec.message();
        return;
    }
    bc::log_info() << "Connection established.";
    // Subscribe to 'inv' packets.
    node->subscribe_inventory(
        std::bind(&tx_sentinel::inventory_received, this,
            ph::_1, ph::_2, node));
    // Resubscribe to new nodes.
    p2p_.subscribe_channel(
        std::bind(&tx_sentinel::connection_started, this, ph::_1, ph::_2));
}

void notify_transaction(
    python::object handle_newtx, const bc::hash_digest& tx_hash)
{
    std::string hash_str(tx_hash.begin(), tx_hash.end());
    pyfunction pyh(handle_newtx);
    pyh(hash_str);
}

void tx_sentinel::inventory_received(const std::error_code& ec,
    const bc::inventory_type& packet, bc::network::channel_ptr node)
{
    if (ec)
    {
        bc::log_error() << "inventory: " << ec.message();
        return;
    }
    for (const bc::inventory_vector_type& ivec: packet.inventories)
    {
        if (ivec.type == bc::inventory_type_id::transaction)
        {
            notify_transaction(handle_newtx_, ivec.hash);
        }
        else if (ivec.type == bc::inventory_type_id::block);
            // Do nothing.
        else
            bc::log_warning() << "Ignoring unknown inventory type";
    }
    // Resubscribe to 'inv' packets.
    node->subscribe_inventory(
        std::bind(&tx_sentinel::inventory_received, this,
            ph::_1, ph::_2, node));
}

size_t tx_sentinel::total_connections() const
{
    return p2p_.total_connections();
}

// Turn tx_sentinel into a copyable object.
// We also need a fixed address if we're binding methods using 'this'
class tx_sentinel_wrapper
{
public:
    typedef std::shared_ptr<tx_sentinel> tx_sentinel_ptr;

    void start(bool display_output,
        size_t threads, size_t number_hosts,
        python::object handle_newtx, python::object handle_start)
    {
        pimpl_->start(display_output, threads, number_hosts,
            handle_newtx, handle_start);
    }
    void stop()
    {
        pimpl_->stop();
    }
    size_t total_connections() const
    {
        return pimpl_->total_connections();
    }

private:
    tx_sentinel_ptr pimpl_ = std::make_shared<tx_sentinel>();
};

BOOST_PYTHON_MODULE(tx_sentinel)
{
    PyEval_InitThreads();

    using namespace boost::python;
    class_<tx_sentinel_wrapper>("TxSentinel")
        .def("start", &tx_sentinel_wrapper::start)
        .def("stop", &tx_sentinel_wrapper::stop)
        .add_property("total_connections",
            &tx_sentinel_wrapper::total_connections);
    ;
}

