#include <boost/python.hpp>
#include <bitcoin/bitcoin.hpp>

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

class broadcaster
{
public:
    broadcaster();

    void start(size_t threads,
        size_t broadcast_hosts, size_t monitor_hosts,
        python::object handle_newtx, python::object handle_start);
    void stop();

    bool broadcast(const std::string raw_tx);

private:
    void connection_started(
        const std::error_code& ec, bc::channel_ptr node);
    void inventory_received(const std::error_code& ec,
        const bc::inventory_type& packet, bc::channel_ptr node);

    std::ofstream outfile_, errfile_;
    bc::threadpool pool_;
    bc::hosts hosts_;
    bc::handshake handshake_;
    bc::network network_;
    bc::protocol broadcast_p2p_, monitor_p2p_;
    python::object handle_newtx_;
};

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
void log_to_both(std::ostream& device, std::ofstream& file,
    bc::log_level level, const std::string& domain, const std::string& body)
{
    if (body.empty())
        return;
    std::ostringstream output;
    output << level_repr(level);
    if (!domain.empty())
        output << " [" << domain << "]";
    output << ": " << body;
    device << output.str() << std::endl;
    file << output.str() << std::endl;
}

void output_file(std::ofstream& file, bc::log_level level,
    const std::string& domain, const std::string& body)
{
    log_to_file(file, level, domain, body);
}
void output_both(std::ofstream& file, bc::log_level level,
    const std::string& domain, const std::string& body)
{
    log_to_both(std::cout, file, level, domain, body);
}

void error_file(std::ofstream& file, bc::log_level level,
    const std::string& domain, const std::string& body)
{
    log_to_file(file, level, domain, body);
}
void error_both(std::ofstream& file, bc::log_level level,
    const std::string& domain, const std::string& body)
{
    log_to_both(std::cerr, file, level, domain, body);
}

broadcaster::broadcaster()
  : hosts_(pool_), handshake_(pool_), network_(pool_),
    broadcast_p2p_(
        pool_, hosts_, handshake_, network_),
    monitor_p2p_(
        pool_, hosts_, handshake_, network_)
{
}

void broadcaster::start(size_t threads,
    size_t broadcast_hosts, size_t monitor_hosts,
    python::object handle_newtx, python::object handle_start)
{
    outfile_.open("debug.log");
    errfile_.open("error.log");
    // Suppress noisy output.
    bc::log_debug().set_output_function(
        std::bind(output_file, std::ref(outfile_), ph::_1, ph::_2, ph::_3));
    bc::log_info().set_output_function(
        std::bind(output_both, std::ref(outfile_), ph::_1, ph::_2, ph::_3));
    bc::log_warning().set_output_function(
        std::bind(error_file, std::ref(errfile_), ph::_1, ph::_2, ph::_3));
    bc::log_error().set_output_function(
        std::bind(error_both, std::ref(errfile_), ph::_1, ph::_2, ph::_3));
    bc::log_fatal().set_output_function(
        std::bind(error_both, std::ref(errfile_), ph::_1, ph::_2, ph::_3));

    pool_.spawn(threads);

    handle_newtx_ = handle_newtx;
    // Set connection counts.
    broadcast_p2p_.set_max_outbound(broadcast_hosts);
    monitor_p2p_.set_max_outbound(monitor_hosts);
    // Notify us of new connections so we can subscribe to 'inv' packets.
    monitor_p2p_.subscribe_channel(
        std::bind(&broadcaster::connection_started, this, ph::_1, ph::_2));
    // Start connecting to p2p networks for broadcasting and monitor txs.
    auto monitor_started = [handle_start](
        const std::error_code& ec)
    {
        pyfunction pyh(handle_start);
        if (ec)
            pyh(ec.message());
        else
            // Success. Pass in None.
            pyh(python::object());
    };
    auto broadcast_started = [this, monitor_started, handle_start](
        const std::error_code& ec)
    {
        pyfunction pyh(handle_start);
        if (ec)
            pyh(ec.message());
        else
            monitor_p2p_.start(monitor_started);
    };
    broadcast_p2p_.start(broadcast_started);
}
void broadcaster::stop()
{
    pool_.stop();
    pool_.join();
}

bool broadcaster::broadcast(const std::string raw_tx)
{
    bc::transaction_type tx;
    try
    {
        satoshi_load(raw_tx.begin(), raw_tx.end(), tx);
    }
    catch (bc::end_of_stream)
    {
        return false;
    }
    // We can ignore the send since we have connections to monitor
    // from the network and resend if neccessary anyway.
    auto ignore_send = [](const std::error_code&, size_t) {};
    broadcast_p2p_.broadcast(tx, ignore_send);
    return true;
}

void broadcaster::connection_started(
    const std::error_code& ec, bc::channel_ptr node)
{
    if (ec)
    {
        bc::log_warning() << "Couldn't start connection: " << ec.message();
        return;
    }
    bc::log_info() << "Connection established.";
    // Subscribe to 'inv' packets.
    node->subscribe_inventory(
        std::bind(&broadcaster::inventory_received, this,
            ph::_1, ph::_2, node));
    // Resubscribe to new nodes.
    monitor_p2p_.subscribe_channel(
        std::bind(&broadcaster::connection_started, this, ph::_1, ph::_2));
}

void notify_transaction(
    python::object handle_newtx, const bc::hash_digest& tx_hash)
{
    std::string hash_str(tx_hash.begin(), tx_hash.end());
    pyfunction pyh(handle_newtx);
    pyh(hash_str);
}

void broadcaster::inventory_received(const std::error_code& ec,
    const bc::inventory_type& packet, bc::channel_ptr node)
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
        std::bind(&broadcaster::inventory_received, this,
            ph::_1, ph::_2, node));
}

// Turn broadcaster into a copyable object.
// We also need a fixed address if we're binding methods using 'this'
class broadcaster_wrapper
{
public:
    typedef std::shared_ptr<broadcaster> broadcaster_ptr;

    void start(size_t threads,
        size_t broadcast_hosts, size_t monitor_hosts,
        python::object handle_newtx, python::object handle_start)
    {
        pimpl_->start(threads, broadcast_hosts, monitor_hosts,
            handle_newtx, handle_start);
    }
    void stop()
    {
        pimpl_->stop();
    }

    bool broadcast(const std::string raw_tx)
    {
        return pimpl_->broadcast(raw_tx);
    }

private:
    broadcaster_ptr pimpl_ = std::make_shared<broadcaster>();
};

BOOST_PYTHON_MODULE(_brc)
{
    PyEval_InitThreads();

    using namespace boost::python;
    class_<broadcaster_wrapper>("Broadcaster")
        .def("start", &broadcaster_wrapper::start)
        .def("stop", &broadcaster_wrapper::stop)
        .def("broadcast", &broadcaster_wrapper::broadcast)
    ;
}

